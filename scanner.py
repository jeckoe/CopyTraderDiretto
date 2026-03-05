from pyrogram import Client
from gestoreDB import insertDialog


async def scan_and_save(app: Client, user_id: int) -> list[dict]:
    """
    Legge tutti i dialog dell'account e li salva nel DB.
    Ritorna anche la lista come dizionari, utile per mostrarli a schermo.
    """
    chats = []

    async for dialog in app.get_dialogs():
        chat = dialog.chat
        tipo = chat.type.name
        nome = chat.title or f"{chat.first_name or ''} {chat.last_name or ''}".strip()

        entry = {"id": str(chat.id), "tipo": tipo, "nome": nome}
        insertDialog(user_id, entry)
        chats.append(entry)

    return chats
