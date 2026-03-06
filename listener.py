# listener.py
import logging
from pyrogram import Client, idle
from pyrogram.handlers import MessageHandler

from User import User
from analyzer import analyze

logger = logging.getLogger(__name__)


def build_message_handler(usr: User):
    """
    Ritorna la funzione _on_message con usr "inglobato" dentro.
    Questo si chiama closure — _on_message ricorda usr anche se
    Pyrogram la chiama senza passarglielo esplicitamente.
    """

    async def _on_message(client: Client, message) -> None:
        text = message.text or message.caption
        if text is None:
            return

        sender = message.from_user or message.sender_chat
        sender_id = str(sender.id) if sender else None
        chat_id = str(message.chat.id)

        logger.info(f"[LISTENER] chat={chat_id} sender={sender_id} text={text}")

        signal = analyze(usr, chat_id, sender_id, text)

        if signal is not None:
            print(f"\n🔔 SEGNALE TROVATO")
            print(f"   Symbol : {signal.symbol}")
            print(f"   Action : {signal.action}")
            print(f"   Entry  : {signal.entry}")
            print(f"   SL     : {signal.sl}")
            print(f"   TP     : {signal.tp}")
            print(f"   Chat   : {signal.source_chat_id}")
            print(f"   Time   : {signal.timestamp}")

            logger.info(
                f"[SIGNAL] symbol={signal.symbol} action={signal.action} "
                f"entry={signal.entry} sl={signal.sl} tp={signal.tp} "
                f"chat={signal.source_chat_id}"
            )

    return _on_message


async def start_listener(app: Client, usr: User) -> None:
    handler = build_message_handler(usr)
    app.add_handler(MessageHandler(handler))
    print("[LISTENER] In ascolto...")
    await idle()
    await app.stop()
