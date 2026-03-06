from pyrogram import Client

from gestoreDB import insertDialog


async def scan_and_save(app: Client, user_id: int) -> tuple[int, int]:
    """
    Legge tutti i dialog e li salva nel DB.
    Ritorna (totale, nuovi) — nuovi = quelli non presenti prima.
    """
    totale = 0
    nuovi = 0

    async for dialog in app.get_dialogs():
        chat = dialog.chat
        tipo = chat.type.name
        nome = chat.title or f"{chat.first_name or ''} {chat.last_name or ''}".strip()

        entry = {"id": str(chat.id), "tipo": tipo, "nome": nome}
        inserito = insertDialog(user_id, entry)
        totale += 1
        if inserito:
            nuovi += 1

    return totale, nuovi
