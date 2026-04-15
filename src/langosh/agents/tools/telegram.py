"""Telegram messaging tools for LangGraph agents — send messages and ask questions with HITL."""

import logging

from langgraph.types import interrupt

logger = logging.getLogger(__name__)


async def send_telegram_message(chat_id: str, message: str, *, get_token) -> str:
    """Send a message to a Telegram chat.

    Args:
        chat_id: Telegram chat ID (numeric string)
        message: The message text to send
        get_token: Async callable that returns the Telegram bot token

    Returns:
        Confirmation with chat ID and message ID
    """
    from telegram import Bot

    token = await get_token("telegram")
    if not token:
        return "Error: Telegram bot token not configured."

    bot = Bot(token=token)
    msg = await bot.send_message(chat_id=int(chat_id), text=message)
    return f"Message sent to chat {chat_id} (message_id: {msg.message_id})"


async def ask_telegram(chat_id: str, question: str, *, get_token) -> str:
    """Send a question to a Telegram chat and wait for a reply.

    The agent will pause (via LangGraph interrupt) until someone replies
    in the Telegram chat.

    Args:
        chat_id: Telegram chat ID (numeric string)
        question: The question to ask
        get_token: Async callable that returns the Telegram bot token

    Returns:
        The reply text from Telegram
    """
    from telegram import Bot

    token = await get_token("telegram")
    if not token:
        return "Error: Telegram bot token not configured."

    bot = Bot(token=token)
    msg = await bot.send_message(chat_id=int(chat_id), text=question)

    # Pause the graph — on resume, interrupt() returns the user's reply
    response = interrupt({
        "platform": "telegram",
        "chat_id": chat_id,
        "message_id": msg.message_id,
        "question": question,
    })
    return str(response)
