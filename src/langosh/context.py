"""Conversation context management — sliding window with rolling summary."""

import langosh.state as state


def _get_summary(mode: str) -> str:
    if mode == "chat":
        return state.chat_summary
    elif mode == "agent":
        return state.agent_summary
    return state.code_summary


def _set_summary(mode: str, text: str) -> None:
    if mode == "chat":
        state.chat_summary = text
    elif mode == "agent":
        state.agent_summary = text
    else:
        state.code_summary = text


def update_summary(mode: str, exiting_messages: list[dict], provider: str, model_id: str) -> None:
    """Incrementally update the rolling summary with messages exiting the window."""
    import asyncio

    from .llm import call_llm_simple

    current_summary = _get_summary(mode)

    exiting_text = "\n".join(
        f"{m['role']}: {m['content'][:500] if isinstance(m.get('content'), str) else '(tool interaction)'}"
        for m in exiting_messages
    )

    prompt = exiting_text
    if current_summary:
        prompt = f"Existing summary:\n{current_summary}\n\nNew messages to incorporate:\n{exiting_text}"

    state.console.print("[dim]Updating conversation summary...[/dim]")
    result = asyncio.run(
        call_llm_simple(
            provider=provider,
            model_id=model_id,
            api_key=None,
            system="Summarize this conversation concisely. Preserve key facts, decisions, file paths, and context. Be brief — under 500 words.",
            messages=[{"role": "user", "content": prompt}],
        )
    )

    _set_summary(mode, result["text"])


def apply_window(mode: str, messages: list[dict], provider: str, model_id: str) -> list[dict]:
    """Apply the sliding window: trim messages beyond WINDOW_SIZE and update summary."""
    summary = _get_summary(mode)

    if len(messages) <= state.WINDOW_SIZE:
        if summary:
            return [{"role": "user", "content": f"[Conversation context: {summary}]"}] + messages
        return messages

    overflow = len(messages) - state.WINDOW_SIZE
    exiting = messages[:overflow]
    window = messages[overflow:]

    update_summary(mode, exiting, provider, model_id)

    messages[:] = window

    summary = _get_summary(mode)
    return [{"role": "user", "content": f"[Conversation context: {summary}]"}] + window
