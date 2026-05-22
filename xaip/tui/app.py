"""
XAIP TUI — interfaz de texto con Textual
xaip tui [--collection name] [--env name]
"""
from __future__ import annotations

import asyncio
import json
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Label,
    Log,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
    Tree,
)
from textual.widgets.tree import TreeNode


class XaipTUI(App):
    """XAIP — Terminal UI para explorar y ejecutar colecciones."""

    TITLE = "XAIP API Tester"
    CSS = """
    Screen {
        layout: horizontal;
    }
    #sidebar {
        width: 30;
        border: round $primary;
        padding: 1;
    }
    #main {
        width: 1fr;
    }
    #details {
        height: 1fr;
        border: round $secondary;
        padding: 1;
        overflow-y: scroll;
    }
    #log {
        height: 12;
        border: round $warning;
    }
    DataTable {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Salir"),
        Binding("r", "run_selected", "Ejecutar"),
        Binding("e", "toggle_endpoints", "Endpoints"),
        Binding("c", "toggle_collections", "Colecciones"),
        Binding("?", "show_help", "Ayuda"),
    ]

    current_node: reactive[str | None] = reactive(None)

    def __init__(self, config_path: str | None = None, env: str | None = None, collection: str | None = None):
        super().__init__()
        self._config_path = config_path
        self._env_name = env
        self._collection_filter = collection
        self._cfg = None
        self._active_env = None

    def on_mount(self) -> None:
        self._load_config()
        self._build_tree()

    def _load_config(self) -> None:
        from xaip.core.config_repo import ConfigRepository
        from xaip.commands.utils import resolve_env
        repo = ConfigRepository(self._config_path)
        self._cfg = repo.load()
        self._active_env = resolve_env(self._cfg, self._env_name)

    def _build_tree(self) -> None:
        tree: Tree = self.query_one("#nav-tree")
        tree.clear()

        cfg = self._cfg
        if not cfg:
            return

        # Endpoints
        ep_root = tree.root.add("📡 Endpoints", expand=True)
        controllers: dict[str, list] = {}
        for ep in cfg.endpoints:
            ctrl = ep.controller or "misc"
            controllers.setdefault(ctrl, []).append(ep)

        for ctrl_name, eps in controllers.items():
            ctrl_node = ep_root.add(ctrl_name)
            for ep in eps:
                ctrl_node.add_leaf(f"[{ep.method.value}] {ep.path}", data={"type": "endpoint", "id": ep.id})

        # Colecciones
        col_root = tree.root.add("📋 Colecciones", expand=True)
        for col in cfg.collections:
            if self._collection_filter and col.id != self._collection_filter:
                continue
            col_node = col_root.add(col.name, data={"type": "collection", "id": col.id})
            for step in col.steps:
                col_node.add_leaf(
                    f"[{step.request.method.value}] {step.request.path}",
                    data={"type": "step", "collection": col.id, "id": step.id}
                )

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="sidebar"):
                yield Label("[b]XAIP[/b]", markup=True)
                yield Tree("Workspace", id="nav-tree")
            with Vertical(id="main"):
                with TabbedContent():
                    with TabPane("Detalle", id="tab-details"):
                        yield Static("Selecciona un ítem del árbol.", id="details")
                    with TabPane("Historial", id="tab-history"):
                        yield self._make_history_table()
                    with TabPane("Entorno", id="tab-env"):
                        yield self._make_env_table()
                yield RichLog(id="log", highlight=True, markup=True)
        yield Footer()

    def _make_history_table(self) -> DataTable:
        t = DataTable(id="history-table")
        t.add_columns("Run ID", "Colección", "Status", "Duración")
        if self._cfg:
            for run in self._cfg.history[-20:]:
                icon = "✅" if run.exit_code == 0 else "❌"
                t.add_row(run.id, run.collection or "-", icon, f"{run.duration_ms}ms")
        return t

    def _make_env_table(self) -> DataTable:
        t = DataTable(id="env-table")
        t.add_columns("Variable", "Valor")
        if self._active_env:
            for k, v in self._active_env.vars.items():
                t.add_row(k, v)
        return t

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        data = event.node.data
        if not data:
            return
        self._show_details(data)

    def _show_details(self, data: dict) -> None:
        details: Static = self.query_one("#details")
        log: RichLog = self.query_one("#log")

        if data["type"] == "endpoint":
            ep = self._cfg.get_endpoint(data["id"])
            if ep:
                info = ep.model_dump(by_alias=True, exclude_none=True)
                details.update(f"[b]Endpoint[/b]\n```\n{json.dumps(info, indent=2)}\n```")
        elif data["type"] == "collection":
            col = self._cfg.get_collection(data["id"])
            if col:
                info = {"id": col.id, "name": col.name, "steps": len(col.steps)}
                details.update(
                    f"[b]{col.name}[/b] — {len(col.steps)} pasos\n"
                    + "\n".join(f"  {i+1}. [{s.request.method.value}] {s.request.path}" for i, s in enumerate(col.steps))
                )
        elif data["type"] == "step":
            col = self._cfg.get_collection(data["collection"])
            if col:
                step = next((s for s in col.steps if s.id == data["id"]), None)
                if step:
                    info = step.model_dump(by_alias=True, exclude_none=True)
                    details.update(f"[b]Step: {step.id}[/b]\n{json.dumps(info, indent=2)}")

        self.current_node = str(data)

    async def action_run_selected(self) -> None:
        log: RichLog = self.query_one("#log")
        node = self.query_one("#nav-tree").cursor_node
        if not node or not node.data:
            log.write("[yellow]Selecciona un paso o colección para ejecutar.[/yellow]")
            return

        data = node.data
        if data["type"] == "collection":
            await self._run_collection(data["id"])
        elif data["type"] == "step":
            await self._run_step(data["collection"], data["id"])

    async def _run_collection(self, col_id: str) -> None:
        log: RichLog = self.query_one("#log")
        log.write(f"[cyan]▶ Ejecutando colección '{col_id}'...[/cyan]")
        from xaip.core.runner import CollectionRunner
        col = self._cfg.get_collection(col_id)
        if not col:
            return

        def on_start(sid: str) -> None:
            log.write(f"  [dim]→ {sid}[/dim]")

        def on_end(result) -> None:
            icon = "✅" if result.status.value == "passed" else "❌"
            log.write(f"  {icon} {result.id} — {result.duration_ms}ms")

        runner = CollectionRunner(self._active_env, on_step_start=on_start, on_step_end=on_end)
        run_result = await runner.run(col)
        log.write(f"[green]Completado: {run_result.summary}[/green]")

    async def _run_step(self, col_id: str, step_id: str) -> None:
        log: RichLog = self.query_one("#log")
        log.write(f"[cyan]▶ Ejecutando paso '{step_id}'...[/cyan]")
        from xaip.core.runner import CollectionRunner
        col = self._cfg.get_collection(col_id)
        if not col:
            return
        runner = CollectionRunner(self._active_env)
        run_result = await runner.run(col, only=[step_id])
        for s in run_result.steps:
            icon = "✅" if s.status.value == "passed" else "❌"
            log.write(f"{icon} {s.id} — {s.duration_ms}ms")
            if s.response:
                log.write(f"   Status: {s.response.get('status', '?')}")

    def action_toggle_endpoints(self) -> None:
        self.notify("Foco en Endpoints")

    def action_toggle_collections(self) -> None:
        self.notify("Foco en Colecciones")

    def action_show_help(self) -> None:
        self.notify(
            "r: Ejecutar | q: Salir | e: Endpoints | c: Colecciones",
            severity="information",
            timeout=4.0,
        )
