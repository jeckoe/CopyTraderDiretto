# listener.py
import logging
from pyrogram import Client, idle
from pyrogram.handlers import MessageHandler

logger = logging.getLogger(__name__)


async def _on_message(client: Client, message) -> None:
    text = message.text or message.caption
    if text is None:
        return

    sender = message.from_user or message.sender_chat
    sender_id = sender.id if sender else "unknown"

    logger.info(f"[MSG] chat={message.chat.id} sender={sender_id} text={text[:80]}")
    # TODO: push to analyzer queue


async def start_listener(app: Client) -> None:
    app.add_handler(MessageHandler(_on_message))
    print("[LISTENER] In ascolto...")
    await idle()          # ← funzione standalone, non metodo del client
    await app.stop()      # ← quando idle() termina (es. CTRL+C), chiude pulito