"""Slack messaging tools for LangGraph agents — send messages and ask questions with HITL."""

import logging
import re

from langgraph.types import interrupt

logger = logging.getLogger(__name__)


def _markdown_to_mrkdwn(text: str) -> str:
    """Convert Markdown to Slack mrkdwn format."""
    text = re.sub(r'\*\*(.+?)\*\*', r'*\1*', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'<\2|\1>', text)
    text = re.sub(r'^#{1,6}\s+(.+)$', r'*\1*', text, flags=re.MULTILINE)
    text = re.sub(r'^- ', '• ', text, flags=re.MULTILINE)
    text = re.sub(r'^---+$', '───', text, flags=re.MULTILINE)
    return text


async def send_slack_message(channel: str, message: str, thread_ts: str = "", *, get_token) -> str:
    """Send a message to a Slack channel, optionally as a thread reply.

    Args:
        channel: Slack channel name or ID (e.g. '#general' or 'C1234567890')
        message: The message text to send
        thread_ts: Optional thread timestamp to reply in a thread
        get_token: Async callable that returns the Slack API token

    Returns:
        Confirmation with channel and timestamp
    """
    from slack_sdk import WebClient

    token = await get_token("slack")
    if not token:
        return "Error: Slack API token not configured."

    client = WebClient(token=token)
    kwargs = {"channel": channel, "text": _markdown_to_mrkdwn(message)}
    if thread_ts:
        kwargs["thread_ts"] = thread_ts
    result = client.chat_postMessage(**kwargs)
    return f"Message sent to {channel} (ts: {result['ts']})"


async def ask_slack(channel: str, question: str, *, get_token) -> str:
    """Send a question to a Slack channel and wait for a reply.

    The agent will pause (via LangGraph interrupt) until someone replies
    in the Slack thread.

    Args:
        channel: Slack channel name or ID
        question: The question to ask
        get_token: Async callable that returns the Slack API token

    Returns:
        The reply text from Slack, plus the thread_ts for follow-up messages.
    """
    from slack_sdk import WebClient

    token = await get_token("slack")
    if not token:
        return "Error: Slack API token not configured."

    client = WebClient(token=token)
    result = client.chat_postMessage(channel=channel, text=question)
    thread_ts = result["ts"]
    channel_id = result["channel"]

    client.chat_postMessage(
        channel=channel_id,
        text="Please reply in this thread.",
        thread_ts=thread_ts,
    )

    # Pause the graph — on resume, interrupt() returns the user's reply
    response = interrupt({
        "platform": "slack",
        "channel": channel_id,
        "thread_ts": thread_ts,
        "question": question,
    })

    return f"User replied: {response}\n\nIMPORTANT: To reply in the same Slack thread, use send_slack_message with thread_ts=\"{thread_ts}\""
