import sqlite3
from User import User
from datetime import datetime
import logging

logger = logging.getLogger(__name__)
CONST_PATH_DB = "diretto.db"
isDBStarted = False
connection = None


# ──────────────────────────────────────────────
# Gestione connessione
# ──────────────────────────────────────────────
def startDB(forceReset=False) -> None:
    global isDBStarted, connection
    if forceReset:
        isDBStarted = False
        connection.close()
    if not isDBStarted:
        connection = sqlite3.connect(CONST_PATH_DB)
        connection.execute("PRAGMA foreign_keys = ON")  # attiva i vincoli FK
        isDBStarted = True


# ──────────────────────────────────────────────
# Utenti e configurazione Telegram
# ──────────────────────────────────────────────
def getUser(username, password) -> User:
    startDB()
    global connection
    result = connection.execute(
        "SELECT ID_UTENTE FROM USERS WHERE USERNAME = ? AND PASSWORD = ?",
        (username, password)
    ).fetchone()
    if result is None:
        raise ValueError("Credenziali non valide")
    return User(result[0])


def getTelegramConfig(usr) -> tuple:
    if not isinstance(usr, User):
        raise TypeError("utente must be a User")
    startDB()
    global connection
    fetched = connection.execute(
        "SELECT API_ID, API_HASH, TEL_NUMBER, SESSION_NAME, SESSION_STRING FROM TCONFIG WHERE ID_UTENTE = ?",
        (usr.ID,)
    ).fetchone()
    if fetched is not None:
        usr.API_ID = fetched[0]
        usr.API_HASH = fetched[1]
        usr.TEL_NUMBER = fetched[2]
        usr.SESSION_NAME = fetched[3]
        usr.SESSION_STRING = fetched[4]
        return usr, True
    return usr, False


def saveSession(utente, session_string) -> None:
    startDB()
    global connection

    # Verifica che il record esista per quell'utente
    row = connection.execute(
        "SELECT ID_UTENTE FROM TCONFIG WHERE ID_UTENTE = ?",
        (utente.ID,)
    ).fetchone()

    if row is None:
        # Non esiste ancora nessuna riga per questo utente
        logger.error(f"saveSession: nessun record in TCONFIG per ID_UTENTE={utente.ID}")
        return

    result = connection.execute(
        "UPDATE TCONFIG SET SESSION_STRING = ? WHERE ID_UTENTE = ?",
        (session_string, utente.ID)
    )
    connection.commit()

    if result.rowcount == 0:
        logger.error(f"saveSession: UPDATE non ha modificato nessuna riga per ID_UTENTE={utente.ID}")
    else:
        logger.info(f"saveSession: SESSION_STRING aggiornata per ID_UTENTE={utente.ID}")


# ──────────────────────────────────────────────
# Dialog
# ──────────────────────────────────────────────
def insertDialog(ID, chat) -> None:
    startDB()
    global connection
    # INSERT OR IGNORE evita duplicati grazie al UNIQUE (ID_UTENTE, DIALOG_ID)
    connection.execute(
        "INSERT OR IGNORE INTO DIALOGS(ID_UTENTE, TYPE, DIALOG_ID, DIALOG_NAME) VALUES (?, ?, ?, ?)",
        (ID, chat["tipo"], chat["id"], chat["nome"])
    )
    connection.commit()


def getActiveDialogs(usr: User) -> list[dict]:
    """Ritorna solo i dialog con IS_ACTIVE = 1 per quell'utente."""
    startDB()
    global connection
    rows = connection.execute(
        "SELECT ID, DIALOG_ID, DIALOG_NAME, TYPE FROM DIALOGS WHERE ID_UTENTE = ? AND IS_ACTIVE = 1",
        (usr.ID,)
    ).fetchall()
    return [{"pk": r[0], "dialog_id": r[1], "nome": r[2], "tipo": r[3]} for r in rows]


# ──────────────────────────────────────────────
# Keyword del parser (globali + per canale)
# ──────────────────────────────────────────────
def getSignalKeywords(usr: User, dialog_pk: int | None = None) -> dict[str, list[str]]:
    """
    Carica le keyword con logica gerarchica:
    1. Prima carica le regole globali (DIALOG_ID IS NULL)
    2. Se dialog_pk è specificato, le regole specifiche vengono aggiunte/sovrascritte

    Ritorna un dict tipo:
    {
        "BUY":   ["buy", "long", "acheter"],
        "SELL":  ["sell", "short"],
        "SL":    ["sl", "stop loss"],
        ...
    }
    """
    startDB()
    global connection

    # Regole globali
    rows = connection.execute(
        "SELECT KEYWORD_TYPE, KEYWORD FROM SIGNAL_KEYWORDS "
        "WHERE ID_UTENTE = ? AND DIALOG_ID IS NULL",
        (usr.ID,)
    ).fetchall()

    # Costruisce il dict partendo dalle globali
    keywords: dict[str, list[str]] = {}
    for ktype, kword in rows:
        keywords.setdefault(ktype, []).append(kword.lower())

    # Aggiunge/sovrascrive con le specifiche del canale se richiesto
    if dialog_pk is not None:
        rows_specific = connection.execute(
            "SELECT KEYWORD_TYPE, KEYWORD FROM SIGNAL_KEYWORDS "
            "WHERE ID_UTENTE = ? AND DIALOG_ID = ?",
            (usr.ID, dialog_pk)
        ).fetchall()
        for ktype, kword in rows_specific:
            keywords.setdefault(ktype, []).append(kword.lower())

    return keywords


def getSkipKeywords(usr: User, dialog_pk: int | None = None) -> list[str]:
    """
    Carica le skip keywords con la stessa logica gerarchica.
    Ritorna una lista flat di parole da ignorare.
    """
    startDB()
    global connection

    rows = connection.execute(
        "SELECT KEYWORD FROM SKIP_KEYWORDS WHERE ID_UTENTE = ? AND DIALOG_ID IS NULL",
        (usr.ID,)
    ).fetchall()
    skip = [r[0].lower() for r in rows]

    if dialog_pk is not None:
        rows_specific = connection.execute(
            "SELECT KEYWORD FROM SKIP_KEYWORDS WHERE ID_UTENTE = ? AND DIALOG_ID = ?",
            (usr.ID, dialog_pk)
        ).fetchall()
        skip += [r[0].lower() for r in rows_specific]

    return skip


# ──────────────────────────────────────────────
# Messaggi non riconosciuti
# ──────────────────────────────────────────────
def saveUnrecognized(usr: User, dialog_id: str, sender_id: str | None, raw_text: str) -> None:
    """Salva un messaggio che il parser non ha saputo interpretare."""
    startDB()
    global connection
    connection.execute(
        "INSERT INTO UNRECOGNIZED_MESSAGES(ID_UTENTE, DIALOG_ID, SENDER_ID, RAW_TEXT, RECEIVED_AT) "
        "VALUES (?, ?, ?, ?, ?)",
        (usr.ID, dialog_id, sender_id, raw_text, datetime.now().isoformat())
    )
    connection.commit()


# ──────────────────────────────────────────────
# Registrazione utente e primo setup Telegram
# ──────────────────────────────────────────────
def registerUser(username: str, password: str) -> User:
    """
    Registra un nuovo utente nel DB.
    Lancia ValueError se lo username esiste già.
    """
    startDB()
    global connection
    try:
        connection.execute(
            "INSERT INTO USERS(USERNAME, PASSWORD) VALUES (?, ?)",
            (username, password)
        )
        connection.commit()
    except sqlite3.IntegrityError:
        raise ValueError(f"Username '{username}' già esistente")

    result = connection.execute(
        "SELECT ID_UTENTE FROM USERS WHERE USERNAME = ?", (username,)
    ).fetchone()
    return User(result[0])


def saveTelegramConfig(usr: User, api_id: int, api_hash: str,
                       tel_number: str, session_name: str,
                       session_string: str = "") -> None:
    """
    Salva la configurazione Telegram per un utente.
    Usata al primo setup, quando TCONFIG è ancora vuota per quell'utente.
    """
    startDB()
    global connection
    connection.execute(
        "INSERT INTO TCONFIG(API_ID, API_HASH, TEL_NUMBER, SESSION_NAME, ID_UTENTE, SESSION_STRING) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (api_id, api_hash, tel_number, session_name, usr.ID, session_string)
    )
    connection.commit()


# ──────────────────────────────────────────────
# Logging su DB
# ──────────────────────────────────────────────
def saveLog(session_id: str, level: str, module: str,
            message: str, user_id: int | None = None) -> None:
    """Salva un log nel DB, correlato all'utente e alla sessione corrente."""
    startDB()
    global connection
    connection.execute(
        "INSERT INTO LOGS(ID_UTENTE, SESSION_ID, LEVEL, MODULE, MESSAGE, CREATED_AT) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, session_id, level, module, message, datetime.now().isoformat())
    )
    connection.commit()


def usernameExists(username: str) -> bool:
    """Controlla se uno username è già registrato, indipendentemente dalla password."""
    startDB()
    global connection
    result = connection.execute(
        "SELECT ID_UTENTE FROM USERS WHERE USERNAME = ?", (username,)
    ).fetchone()
    return result is not None
