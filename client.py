import logging
from pyrogram import Client
from tenacity import AsyncRetrying, stop_after_attempt, wait_exponential, RetryError

from User import User

logger = logging.getLogger(__name__)


def build_client(usr: User) -> Client:
    """Costruisce l'oggetto Client senza ancora connettersi."""
    return Client(
        name=usr.SESSION_NAME,
        api_id=usr.API_ID,
        api_hash=usr.API_HASH,
        phone_number=usr.TEL_NUMBER,
        in_memory=True,
        session_string=usr.SESSION_STRING
    )


async def connect(usr: User, max_retries: int = 5) -> Client | None:
    """
    Tenta la connessione fino a max_retries volte.
    Ritorna il Client connesso, oppure None se tutti i tentativi falliscono.
    """
    try:
        async for attempt in AsyncRetrying(
                stop=stop_after_attempt(max_retries),
                wait=wait_exponential(min=2, max=30),
                before_sleep=lambda s: logger.warning(
                    f"Tentativo {s.attempt_number} fallito. "
                    f"Riprovo tra {s.next_action.sleep:.0f}s..."
                )
        ):
            with attempt:
                app = build_client(usr)
                await app.start()
                return app

    except RetryError:
        logger.error(f"Connessione fallita dopo {max_retries} tentativi.")
        return None
