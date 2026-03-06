import asyncio
import logging
import uuid

from analyzer import load_active_dialogs
from client import connect
from gestoreDB import getUser, getTelegramConfig, registerUser, saveTelegramConfig, saveLog, usernameExists
from listener import start_listener
from scanner import scan_and_save


class DBLogHandler(logging.Handler):
    def __init__(self, session_id: str, user_id: int | None = None):
        super().__init__()
        self.session_id = session_id
        self.user_id = user_id

    def emit(self, record: logging.LogRecord) -> None:
        try:
            saveLog(
                session_id=self.session_id,
                level=record.levelname,
                module=record.name,
                message=self.format(record),
                user_id=self.user_id
            )
        except Exception:
            pass


def setup_logging(session_id: str, user_id: int | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),
            DBLogHandler(session_id, user_id)
        ]
    )


def first_setup(username: str = "") -> None:
    print("\n=== PRIMO SETUP ===")
    if not username:
        username = input("Username: ")
    password = input("Password: ")
    api_id = int(input("Telegram API_ID: "))
    api_hash = input("Telegram API_HASH: ")
    tel_number = input("Numero di telefono (con prefisso, es. +39...): ")

    usr = registerUser(username, password)
    saveTelegramConfig(usr, api_id, api_hash, tel_number, session_name=username)
    print(f"\nUtente '{username}' registrato. Al prossimo avvio verrà richiesto il codice OTP da Telegram.")


async def main():
    session_id = str(uuid.uuid4())

    username = input("Username: ")

    if not usernameExists(username):
        print("[INFO] Utente non trovato.")
        first_setup(username)
        return

    password = input("Password: ")

    try:
        usr, ok = getTelegramConfig(getUser(username, password))
    except ValueError:
        print("[ERRORE] Password errata.")
        return

    setup_logging(session_id, user_id=usr.ID)
    logger = logging.getLogger(__name__)

    if not ok:
        logger.error("Configurazione Telegram non trovata nel DB.")
        return

    app = await connect(usr, max_retries=5)
    if app is None:
        logger.error("Impossibile connettersi a Telegram. Programma terminato.")
        return

    totale, nuovi = await scan_and_save(app, usr.ID)
    print(f"[SCANNER] Scan completato. {totale} dialog totali, {nuovi} nuovi trovati.")
    if nuovi > 0:
        print("[SCANNER] Attiva i nuovi dialog impostando IS_ACTIVE = 1 nel DB.")

    load_active_dialogs(usr)
    await start_listener(app, usr)  # ← usr passato correttamente


if __name__ == "__main__":
    asyncio.run(main())
