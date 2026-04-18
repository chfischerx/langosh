"""Dev mode — local graph development in the langgraph repo."""

import langosh.state as state

from . import Mode, command


def _render_graph_ascii(nodes: list[dict], edges: list[dict]) -> str:
    """Render a definition.json graph as ASCII art using grandalf for layout."""
    from grandalf.graphs import Edge as GEdge
    from grandalf.graphs import Graph as GGraph
    from grandalf.graphs import Vertex
    from grandalf.layouts import SugiyamaLayout

    class _View:
        def __init__(self, w: int, h: int):
            self.w = w
            self.h = h
            self.xy = (0.0, 0.0)

    node_names = ["__start__"] + [n["name"] for n in nodes] + ["__end__"]
    pad = 4
    box_h = 3
    verts = {}
    for name in node_names:
        v = Vertex(name)
        v.view = _View(len(name) + pad, box_h)
        verts[name] = v

    gedges = []
    for e in edges:
        src = verts.get(e.get("from"))
        tgt = verts.get(e.get("to"))
        if src and tgt:
            gedges.append(GEdge(src, tgt, data=e))

    g = GGraph(list(verts.values()), gedges, directed=True)
    comp = g.C[0] if g.C else g
    layout = SugiyamaLayout(comp)
    layout.init_all(roots=[verts["__start__"]])
    layout.draw(N=1.5)

    # Extract positions — grandalf gives center coordinates
    raw = []
    for v in verts.values():
        cx, cy = v.view.xy
        w = v.view.w
        raw.append((v.data, cx, cy, w, box_h))

    # Normalize so min x/y start at 1
    min_x = min(cx - w / 2 for _, cx, _, w, _ in raw)
    min_y = min(cy - box_h / 2 for _, _, cy, _, _ in raw)
    gap_y = 2  # rows between boxes

    positioned = []
    for name, cx, cy, w, h in raw:
        x = int(cx - w / 2 - min_x) + 1
        y = int(cy - h / 2 - min_y) + 1
        positioned.append((name, x, y, w, h))

    # Scale Y: grandalf may pack layers too tight; ensure gap between layers
    layers: dict[int, list] = {}
    for item in positioned:
        layers.setdefault(item[2], []).append(item)
    sorted_ys = sorted(layers.keys())
    y_map = {}
    cur_y = 1
    for ly in sorted_ys:
        y_map[ly] = cur_y
        cur_y += box_h + gap_y
    positioned = [(n, x, y_map[y], w, h) for n, x, y, w, h in positioned]

    canvas_w = max(x + w for _, x, _, w, _ in positioned) + 2
    canvas_h = max(y + box_h for _, _, y, _, _ in positioned) + 2
    canvas = [[" "] * canvas_w for _ in range(canvas_h)]

    def put(x: int, y: int, ch: str) -> None:
        if 0 <= y < canvas_h and 0 <= x < canvas_w:
            canvas[y][x] = ch

    def put_str(x: int, y: int, s: str) -> None:
        for i, ch in enumerate(s):
            put(x + i, y, ch)

    # Draw boxes
    for name, x, y, w, h in positioned:
        put_str(x, y, "+" + "-" * (w - 2) + "+")
        lpad = (w - 2 - len(name)) // 2
        rpad = w - 2 - lpad - len(name)
        put_str(x, y + 1, "|" + " " * lpad + name + " " * rpad + "|")
        put_str(x, y + 2, "+" + "-" * (w - 2) + "+")

    # Draw edges
    rects = {name: (x, y, w, h) for name, x, y, w, h in positioned}
    for e in edges:
        src_name = e.get("from")
        tgt_name = e.get("to")
        if src_name not in rects or tgt_name not in rects:
            continue
        sx, sy, sw, _ = rects[src_name]
        tx, ty, tw, _ = rects[tgt_name]
        src_cx = sx + sw // 2
        src_bot = sy + box_h
        tgt_cx = tx + tw // 2
        tgt_top = ty

        cond = e.get("conditional", False)
        arrow = "v" if not cond else "?"

        if src_cx == tgt_cx:
            for row in range(src_bot, tgt_top):
                put(src_cx, row, "|")
            put(tgt_cx, tgt_top - 1, arrow)
        else:
            mid_y = (src_bot + tgt_top) // 2
            for row in range(src_bot, mid_y):
                put(src_cx, row, "|")
            lo, hi = min(src_cx, tgt_cx), max(src_cx, tgt_cx)
            for col in range(lo, hi + 1):
                put(col, mid_y, "-")
            for row in range(mid_y + 1, tgt_top):
                put(tgt_cx, row, "|")
            put(tgt_cx, tgt_top - 1, arrow)

    return "\n".join("".join(row).rstrip() for row in canvas).rstrip()


class _GitMixin:
    """Shared git commands for dev modes."""

    @command("status", "Show git status")
    def cmd_status(self, parts):
        import subprocess
        result = subprocess.run(["git", "status", "--short"], capture_output=True, text=True)
        output = result.stdout.strip()
        if output:
            state.console.print(output)
        else:
            state.console.print("[dim]Nothing to commit, working tree clean.[/dim]")
        return "continue"

    @command("commit", "Commit all changes")
    def cmd_commit(self, parts):
        import subprocess
        import questionary

        message = parts[1].strip() if len(parts) > 1 else None
        if not message:
            message = questionary.text("Commit message:").ask()
            if not message or not message.strip():
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            message = message.strip()

        result = subprocess.run(["git", "add", "-A"], capture_output=True, text=True)
        if result.returncode != 0:
            state.console.print(f"[red]{result.stderr.strip()}[/red]")
            return "continue"

        result = subprocess.run(["git", "commit", "-m", message], capture_output=True, text=True)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            stdout = result.stdout.strip()
            state.console.print(f"[dim]{stdout or stderr}[/dim]")
        else:
            state.console.print(f"[green]{result.stdout.strip()}[/green]")
        return "continue"

    @command("deploy", "Commit, push, and reload agents on the server")
    def cmd_deploy(self, parts):
        from .exec_ import _deploy
        return _deploy()


class DevMode(_GitMixin, Mode):
    """Dev mode — list, create, and select graphs from the local repo."""

    def path_label(self) -> str:
        server = state.active_server_name
        return f"graphs[{server}]" if server else "graphs"

    def on_enter(self) -> None:
        state.console.print("[bold cyan]Graphs mode.[/bold cyan] Work with local graphs.")
        state.console.print("[dim]Type /help for commands, /back to return.[/dim]")

    @command("list", "List all graphs from the current repo")
    def cmd_list(self, parts):
        from ..agents import registry
        graphs = registry.list_graphs()
        if not graphs:
            from ..agents.registry import langgraph_json_path
            state.console.print(f"[dim]No graphs in {langgraph_json_path()}.[/dim]")
            return "continue"
        for i, (gid, mod) in enumerate(graphs.items(), 1):
            state.console.print(f"  {i}. [cyan]{gid}[/cyan] — {mod}")
        return "continue"

    @command("create", "Create a new graph with LLM guidance")
    def cmd_create(self, parts):
        import questionary
        from ..agents.builder import create_agent

        state.console.print("[bold]Create a new graph[/bold]\n")

        name = questionary.text(
            "Graph name:",
            validate=lambda t: True if t.strip() else "Name cannot be empty",
        ).ask()
        if name is None:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        description = questionary.text(
            "Description (what does this agent do?):",
            validate=lambda t: True if t.strip() else "Description cannot be empty",
        ).ask()
        if description is None:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        instructions = questionary.text(
            "Build instructions (tools, workflow, behavior):",
            multiline=True,
        ).ask()
        if instructions is None or not instructions.strip():
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        cur_provider = state.active_model.get("provider") or ""
        cur_model_id = state.active_model.get("model_id") or ""
        cur_combined = f"{cur_provider}:{cur_model_id}" if cur_provider and cur_model_id else ""

        choices = ["Use server DEFAULT_MODEL (recommended)"]
        if cur_combined:
            choices.append(f"Match CLI active model ({cur_combined})")
        choices.append("Pick from model catalog")
        choices.append("Enter manually (provider:model-id)")

        model_choice = questionary.select("Runtime model for this graph:", choices=choices).ask()
        if model_choice is None:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        if model_choice.startswith("Use server"):
            graph_model = None
        elif model_choice.startswith("Match CLI"):
            graph_model = cur_combined
        elif model_choice.startswith("Pick from"):
            if not state.model_list:
                state.console.print(
                    "[dim]No models cached yet. Run /fetchmodels first "
                    "(or pick 'Enter manually').[/dim]"
                )
                return "continue"
            catalog = sorted(f"{m.provider}:{m.id}" for m in state.model_list)
            graph_model = questionary.autocomplete(
                "Model (type to filter; Tab/arrow to complete):",
                choices=catalog,
                validate=lambda t: (
                    True if t and ":" in t and t in catalog else "Pick one from the list"
                ),
            ).ask()
            if graph_model is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            graph_model = graph_model.strip()
        else:
            graph_model = questionary.text(
                "Model (format: provider:model-id, e.g. anthropic:claude-sonnet-4-5-20250929):",
                validate=lambda t: True if ":" in t and t.strip() else "Expected provider:model-id",
            ).ask()
            if graph_model is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            graph_model = graph_model.strip()

        from ..worker import run_in_background

        def _work():
            summary = create_agent(
                name.strip(), description.strip(), instructions.strip(), graph_model=graph_model,
            )
            state.console.print(f"\n[green]{summary}[/green]")

        run_in_background("Generating graph definition...", _work)
        return "continue"

    @command("select", "Select an existing graph to work with")
    def cmd_select(self, parts):
        import questionary
        from ..agents import registry

        graph_id = parts[1].strip() if len(parts) > 1 else None
        if not graph_id:
            graphs = registry.list_graphs()
            if not graphs:
                state.console.print("[dim]No graphs in langgraph.json. Use /create first.[/dim]")
                return "continue"
            choices = list(graphs.keys())
            choice = questionary.select("Select graph:", choices=choices).ask()
            if choice is None:
                state.console.print("[dim]Cancelled.[/dim]")
                return "continue"
            graph_id = choice

        self._stack.push(DevGraphMode(graph_id))
        return "continue"


class DevGraphMode(_GitMixin, Mode):
    """Selected graph mode — LLM-driven editing with sub-mode control."""

    def __init__(self, graph_id: str):
        self.graph_id = graph_id
        self.llm_mode = state.agent_sub_mode  # normal/plan/auto

    def path_label(self) -> str:
        return f"{self.graph_id}:{self.llm_mode}"

    def on_enter(self) -> None:
        state.active_graph_id = self.graph_id
        state.agent_editing = True
        state.agent_messages.clear()
        state.agent_summary = ""
        state.console.print(
            f"[bold cyan]Editing {self.graph_id} ({self.llm_mode}).[/bold cyan] "
            "Describe what to change."
        )
        state.console.print("[dim]Type /help for commands, /back to exit.[/dim]")

    def on_exit(self) -> None:
        state.active_graph_id = ""
        state.agent_editing = False

    def handle_free_text(self, text: str) -> None:
        from ..agents.editor import send_edit_query
        try:
            send_edit_query(text)
        except KeyboardInterrupt:
            state.console.print("\n[yellow]Interrupted.[/yellow]")
        except Exception as e:
            state.console.print(f"[bold red]Error:[/bold red] {e}")

    @command("normal", "Confirm every destructive operation")
    def cmd_normal(self, parts):
        return self._set_llm_mode("normal", parts)

    @command("plan", "Read-only tools, no edits")
    def cmd_plan(self, parts):
        return self._set_llm_mode("plan", parts)

    @command("auto", "Auto-approve all tool calls")
    def cmd_auto(self, parts):
        return self._set_llm_mode("auto", parts)

    def _set_llm_mode(self, mode: str, parts):
        from ..settings import set as set_setting
        self.llm_mode = mode
        state.agent_sub_mode = mode
        set_setting("agent_sub_mode", mode)
        labels = {
            "normal": "Confirm every destructive operation",
            "plan": "Read-only tools, no edits",
            "auto": "Auto-approve all tool calls",
        }
        state.console.print(f"[bold cyan]{mode}[/bold cyan] [dim]-- {labels[mode]}[/dim]")
        return "continue"

    @command("compile", "Compile the selected graph")
    def cmd_compile(self, parts):
        import json as _json
        from ..agents import codegen, registry

        folder = registry.graph_dir(self.graph_id)
        def_path = folder / "definition.json"
        if not def_path.is_file():
            state.console.print(
                f"[yellow]No definition.json in {folder}.[/yellow]\n"
                "[dim]This looks like a hand-written graph -- edit `__init__.py` "
                "directly, then restart langosh-server.[/dim]"
            )
            return "continue"

        try:
            definition = _json.loads(def_path.read_text())
            funcs_dir = folder / "functions"
            functions: list[dict] = []
            if funcs_dir.is_dir():
                for fn_path in sorted(funcs_dir.glob("*.py")):
                    functions.append({"name": fn_path.stem, "code": fn_path.read_text()})
            init_path = codegen.write_compiled_graph(self.graph_id, definition, functions)
        except Exception as e:
            state.console.print(f"[bold red]Codegen failed:[/bold red] {e}")
            return "continue"

        state.console.print(
            f"[green]Regenerated {init_path}[/green]\n"
            "[dim]Restart langosh-server to apply.[/dim]"
        )
        return "continue"

    @command("test", "Stateless test run against the server")
    def cmd_test(self, parts):
        from .exec_ import _stateless_test
        return _stateless_test(self.graph_id, parts)

    @command("delete", "Delete the selected graph")
    def cmd_delete(self, parts):
        import shutil
        import subprocess
        import questionary
        from ..agents import registry
        from ..settings import get_agents_path

        confirm = questionary.confirm(
            f"Remove graph '{self.graph_id}' from langgraph.json and delete its folder?",
            default=False,
        ).ask()
        if not confirm:
            state.console.print("[dim]Cancelled.[/dim]")
            return "continue"

        removed_entry = registry.remove_graph(self.graph_id)
        folder = registry.graph_dir(self.graph_id)
        removed_folder = False
        if folder.exists():
            shutil.rmtree(folder)
            removed_folder = True

        if removed_entry or removed_folder:
            state.console.print(
                f"[green]Deleted {self.graph_id}.[/green] "
                f"[dim](langgraph.json: {'removed' if removed_entry else 'absent'}, "
                f"folder: {'removed' if removed_folder else 'absent'})[/dim]"
            )
            agents_path = str(get_agents_path())
            subprocess.run(["git", "add", "-A"], cwd=agents_path, capture_output=True)
            result = subprocess.run(
                ["git", "commit", "-m", f"Delete graph: {self.graph_id}"],
                cwd=agents_path, capture_output=True, text=True,
            )
            if result.returncode == 0:
                state.console.print(f"[dim]Committed: {result.stdout.strip().splitlines()[-1]}[/dim]")
                push = subprocess.run(["git", "push"], cwd=agents_path, capture_output=True, text=True)
                if push.returncode == 0:
                    state.console.print("[dim]Pushed to remote.[/dim]")
                else:
                    state.console.print(f"[yellow]Push failed:[/yellow] [dim]{push.stderr.strip()}[/dim]")
            else:
                state.console.print(f"[dim]{result.stdout.strip() or result.stderr.strip()}[/dim]")
            state.console.print("[dim]Restart langosh-server to drop the registered graph.[/dim]")
            # Pop back to dev mode since graph is deleted
            self._stack.pop()
        else:
            state.console.print(f"[red]Nothing found for graph: {self.graph_id}[/red]")
        return "continue"

    @command("preview", "Visualize the selected graph")
    def cmd_preview(self, parts):
        import json as _json
        from ..agents import registry

        folder = registry.graph_dir(self.graph_id)
        def_path = folder / "definition.json"
        if not def_path.is_file():
            state.console.print(f"[yellow]No definition.json in {folder}.[/yellow]")
            return "continue"

        try:
            definition = _json.loads(def_path.read_text())
        except Exception as e:
            state.console.print(f"[bold red]Error reading definition.json:[/bold red] {e}")
            return "continue"

        state.console.print(f"\n[bold]Graph: {self.graph_id}[/bold]")

        if definition.get("type") == "simple":
            tools = definition.get("tools", [])
            tool_node = f"tools ({len(tools)})"
            simple_nodes = [
                {"name": "call_model", "type": "llm"},
            ]
            if tools:
                simple_nodes.append({"name": tool_node, "type": "tool"})
            simple_edges = [
                {"from": "__start__", "to": "call_model", "conditional": False},
            ]
            if tools:
                simple_edges.append({"from": "call_model", "to": tool_node, "conditional": True})
                simple_edges.append({"from": "call_model", "to": "__end__", "conditional": True})
                simple_edges.append({"from": tool_node, "to": "call_model", "conditional": False})
            else:
                simple_edges.append({"from": "call_model", "to": "__end__", "conditional": False})
            state.console.print()
            state.console.print(_render_graph_ascii(simple_nodes, simple_edges))
            if tools:
                state.console.print(f"\n  [dim]Tools: {', '.join(tools)}[/dim]")
            return "continue"

        nodes = definition.get("nodes", [])
        edges = definition.get("edges", [])
        if not nodes:
            state.console.print("[dim]No nodes in definition.[/dim]")
            return "continue"

        state.console.print()
        state.console.print(_render_graph_ascii(nodes, edges))
        return "continue"
