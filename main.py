import asyncio
import logging
import uuid

from gestoreDB import getUser, getTelegramConfig, registerUser, saveTelegramConfig, saveLog
from client import connect
from listener import start_listener


# ──────────────────────────────────────────────
# Handler custom: scrive i log nel DB SQLite
# ──────────────────────────────────────────────
class DBLogHandler(logging.Handler):
    """
    logging.Handler è la classe base di Python per "destinatari" del log.
    Estendendola, possiamo fare in modo che ogni log.info() / log.warning()
    venga scritto automaticamente nel DB invece che solo a schermo.
    """

    def __init__(self, session_id: str, user_id: int | None = None):
        super().__init__()
        self.session_id = session_id
        self.user_id = user_id

    def emit(self, record: logging.LogRecord) -> None:
        # emit() viene chiamata automaticamente da Python ad ogni log
        try:
            saveLog(
                session_id=self.session_id,
                level=record.levelname,
                module=record.name,
                message=self.format(record),
                user_id=self.user_id
            )
        except Exception:
            pass  # il logger non deve mai crashare il programma principale


def setup_logging(session_id: str, user_id: int | None = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(),  # → console
            DBLogHandler(session_id, user_id)  # → DB
        ]
    )


# ──────────────────────────────────────────────
# Flusso primo setup (utente non esiste ancora)
# ──────────────────────────────────────────────
def first_setup() -> None:
    """
    Guida l'utente nella registrazione e nel primo inserimento
    della configurazione Telegram via console.
    """
    print("\n=== PRIMO SETUP ===")
    username = input("Username: ")
    password = input("Password: ")
    api_id = int(input("Telegram API_ID: "))
    api_hash = input("Telegram API_HASH: ")
    tel_number = input("Numero di telefono (con prefisso, es. +39...): ")

    usr = registerUser(username, password)
    saveTelegramConfig(usr, api_id, api_hash, tel_number, session_name=username)
    print(f"\nUtente '{username}' registrato. Al prossimo avvio verrà richiesto il codice OTP da Telegram.")


# ──────────────────────────────────────────────
# Entrypoint
# ──────────────────────────────────────────────
async def main():
    session_id = str(uuid.uuid4())  # ID univoco per questa esecuzione

    # Tenta il login — se l'utente non esiste offre il primo setup
    try:
        usr, ok = getTelegramConfig(getUser('andrea2', '123'))
    except ValueError:
        print("[INFO] Utente non trovato.")
        first_setup()
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

    await start_listener(app)


if __name__ == "__main__":
    asyncio.run(main())
