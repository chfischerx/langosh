"""Shared interactive model picker.

Used by `/create` (per-graph runtime model) and `/initrepo` (example-
graph default model). Returns a `provider:model-id` string, `""` if
the user picked the "Use server DEFAULT_MODEL" option (only offered
when `include_server_default=True`), or `None` if they cancelled.
"""

from __future__ import annotations

import langosh.state as state

_MANUAL_VALIDATE = (
    "Expected 'provider:model-id' (e.g. anthropic:claude-sonnet-4-5-20250929, "
    "openai:gpt-4o, bedrock_converse:global.anthropic.claude-sonnet-4-5-20250929-v1:0)"
)

# `claude_sdk` is a CLI-only provider — it routes to the Claude Agent
# SDK subprocess rather than through LangChain. LangGraph server /
# `init_chat_model` don't know it, so graph-facing pickers filter it
# out while CLI-only contexts keep it available.
LANGCHAIN_EXCLUDE = frozenset({"claude_sdk"})


def _autocomplete_style():
    """High-contrast style for the autocomplete completion menu.

    Current selection uses the same orange (`#f44336`) as questionary's
    default `answer` accent — matching the color the user sees while
    typing answers to the preceding name / description prompts.
    """
    import questionary

    return questionary.Style([
        ("completion-menu", "bg:ansiblack"),
        ("completion-menu.completion", "bg:ansiblack fg:ansiwhite"),
        ("completion-menu.completion.current", "bg:#f44336 fg:ansiwhite bold"),
        ("scrollbar.background", "bg:ansibrightblack"),
        ("scrollbar.button", "bg:ansiwhite"),
    ])


def pick_model(
    prompt: str,
    *,
    include_server_default: bool = False,
    include_active: bool = True,
    exclude_providers: frozenset[str] | set[str] = frozenset(),
) -> str | None:
    """Show the three- or four-way model picker.

    `exclude_providers` filters the catalog/active/manual entries. Pass
    `LANGCHAIN_EXCLUDE` when picking a model the deployed graph will
    run through `init_chat_model` (which doesn't know our CLI-only
    `claude_sdk` provider)."""
    import questionary

    cur_provider = state.active_model.get("provider") or ""
    cur_model_id = state.active_model.get("model_id") or ""
    active_excluded = cur_provider in exclude_providers
    cur_combined = (
        f"{cur_provider}:{cur_model_id}"
        if cur_provider and cur_model_id and not active_excluded
        else ""
    )

    _SERVER = "Use server DEFAULT_MODEL (recommended)"
    _ACTIVE = f"Match CLI active model ({cur_combined})" if cur_combined else ""
    _CATALOG = "Pick from model catalog"
    _MANUAL = "Enter manually (provider:model-id)"

    choices: list[str] = []
    if include_server_default:
        choices.append(_SERVER)
    if include_active and _ACTIVE:
        choices.append(_ACTIVE)
    choices.append(_CATALOG)
    choices.append(_MANUAL)

    choice = questionary.select(prompt, choices=choices).ask()
    if choice is None:
        return None

    if choice == _SERVER:
        return ""
    if choice == _ACTIVE:
        return cur_combined
    if choice == _CATALOG:
        visible = [m for m in state.model_list if m.provider not in exclude_providers]
        if not visible:
            if state.model_list and exclude_providers:
                only_excluded = {m.provider for m in state.model_list} <= set(exclude_providers)
                if only_excluded:
                    state.console.print(
                        "[yellow]Cached catalog only has CLI-only providers "
                        f"({', '.join(sorted(exclude_providers))}), which can't run in the "
                        "deployed graph.[/yellow] [dim]Run [cyan]/models /fetch[/cyan] to "
                        "populate Anthropic / OpenAI / Bedrock entries, or enter one manually "
                        "below.[/dim]"
                    )
                else:
                    state.console.print(
                        "[dim]No LangChain-compatible models in the catalog. Enter one "
                        "manually below.[/dim]"
                    )
            else:
                state.console.print(
                    "[dim]No models cached yet. Run [cyan]/models /fetch[/cyan] first, "
                    "or enter one manually below.[/dim]"
                )
            # Fall through to the manual entry so the user isn't stuck.
        else:
            catalog = sorted(f"{m.provider}:{m.id}" for m in visible)
            picked = questionary.autocomplete(
                "Model (type to filter; Tab/arrow to complete):",
                choices=catalog,
                validate=lambda t: (
                    True if t and ":" in t and t in catalog else "Pick one from the list"
                ),
                style=_autocomplete_style(),
            ).ask()
            if picked is None:
                return None
            return picked.strip()

    # Manual
    def _validate_manual(t: str) -> bool | str:
        t = t.strip()
        if not t or ":" not in t:
            return _MANUAL_VALIDATE
        prov = t.split(":", 1)[0]
        if prov in exclude_providers:
            return (
                f"Provider {prov!r} is CLI-only and not supported by the "
                "deployed graph. Pick a LangChain-compatible provider."
            )
        return True

    picked = questionary.text(
        "Model (format: provider:model-id):",
        validate=_validate_manual,
    ).ask()
    if picked is None:
        return None
    return picked.strip()
