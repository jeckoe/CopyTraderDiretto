import logging
import sqlite3
from datetime import datetime

from User import User

logger = logging.getLogger(__name__)
CONST_PATH_DB = "diretto.db"
isDBStarted = False
connection = None


# ──────────────────────────────────────────────
# Gestione connessione
# ──────────────────────────────────────────────
_SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS USERS (
    ID_UTENTE   INTEGER PRIMARY KEY AUTOINCREMENT,
    USERNAME    TEXT    NOT NULL UNIQUE,
    PASSWORD    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS TCONFIG (
    ID             INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_UTENTE      INTEGER NOT NULL UNIQUE REFERENCES USERS(ID_UTENTE),
    API_ID         INTEGER NOT NULL,
    API_HASH       TEXT    NOT NULL,
    TEL_NUMBER     TEXT    NOT NULL,
    SESSION_NAME   TEXT    NOT NULL,
    SESSION_STRING TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS DIALOGS (
    ID             INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_UTENTE      INTEGER NOT NULL REFERENCES USERS(ID_UTENTE),
    TYPE           TEXT    NOT NULL,
    DIALOG_ID      TEXT    NOT NULL,
    DIALOG_NAME    TEXT,
    IS_ACTIVE      INTEGER NOT NULL DEFAULT 0,
    SIGNAL_PATTERN TEXT    DEFAULT NULL,
    MT5_ACCOUNT_ID INTEGER DEFAULT NULL REFERENCES MT5_ACCOUNTS(ID),
    UNIQUE(ID_UTENTE, DIALOG_ID)
);

CREATE TABLE IF NOT EXISTS SIGNAL_KEYWORDS (
    ID           INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_UTENTE    INTEGER NOT NULL REFERENCES USERS(ID_UTENTE),
    DIALOG_ID    INTEGER DEFAULT NULL REFERENCES DIALOGS(ID),
    KEYWORD_TYPE TEXT    NOT NULL,
    KEYWORD      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS SKIP_KEYWORDS (
    ID        INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_UTENTE INTEGER NOT NULL REFERENCES USERS(ID_UTENTE),
    DIALOG_ID INTEGER DEFAULT NULL REFERENCES DIALOGS(ID),
    KEYWORD   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS SIGNALS (
    ID          INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_UTENTE   INTEGER NOT NULL REFERENCES USERS(ID_UTENTE),
    DIALOG_ID   TEXT    NOT NULL,
    SENDER_ID   TEXT,
    SYMBOL      TEXT    NOT NULL,
    ACTION      TEXT    NOT NULL,
    ENTRY       REAL,
    SL          REAL,
    RAW_TEXT    TEXT,
    RECEIVED_AT TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS SIGNAL_TP (
    ID        INTEGER PRIMARY KEY AUTOINCREMENT,
    SIGNAL_ID INTEGER NOT NULL REFERENCES SIGNALS(ID),
    LEVEL     INTEGER NOT NULL,
    PRICE     REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS UNRECOGNIZED_MESSAGES (
    ID          INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_UTENTE   INTEGER REFERENCES USERS(ID_UTENTE),
    DIALOG_ID   TEXT,
    SENDER_ID   TEXT,
    RAW_TEXT    TEXT,
    RECEIVED_AT TEXT
);

CREATE TABLE IF NOT EXISTS LOGS (
    ID         INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_UTENTE  INTEGER REFERENCES USERS(ID_UTENTE),
    SESSION_ID TEXT,
    LEVEL      TEXT,
    MODULE     TEXT,
    MESSAGE    TEXT,
    CREATED_AT TEXT
);

CREATE TABLE IF NOT EXISTS MT5_ACCOUNTS (
    ID        INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_UTENTE INTEGER NOT NULL REFERENCES USERS(ID_UTENTE),
    LOGIN     TEXT    NOT NULL,
    PASSWORD  TEXT    NOT NULL,
    SERVER    TEXT    NOT NULL,
    LABEL     TEXT,
    LOT_SIZE  REAL    NOT NULL DEFAULT 0.01
);

CREATE TABLE IF NOT EXISTS SYMBOLS (
    ID             INTEGER PRIMARY KEY AUTOINCREMENT,
    ID_UTENTE      INTEGER NOT NULL REFERENCES USERS(ID_UTENTE),
    MT5_ACCOUNT_ID INTEGER REFERENCES MT5_ACCOUNTS(ID),
    SYMBOL_TG      TEXT    NOT NULL,
    SYMBOL_MT5     TEXT    NOT NULL
);
"""


_MIGRATIONS = [
    # Aggiunge LOT_SIZE a MT5_ACCOUNTS se manca (DB pre-esistenti)
    "ALTER TABLE MT5_ACCOUNTS ADD COLUMN LOT_SIZE REAL NOT NULL DEFAULT 0.01",
    # Aggiunge MT5_ACCOUNT_ID a DIALOGS se manca
    "ALTER TABLE DIALOGS ADD COLUMN MT5_ACCOUNT_ID INTEGER REFERENCES MT5_ACCOUNTS(ID)",
]


def startDB(forceReset=False) -> None:
    global isDBStarted, connection
    if forceReset:
        isDBStarted = False
        connection.close()
    if not isDBStarted:
        connection = sqlite3.connect(CONST_PATH_DB)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(_SCHEMA)
        # Migrazioni incrementali: ignora errori se la colonna esiste già
        for migration in _MIGRATIONS:
            try:
                connection.execute(migration)
                connection.commit()
            except sqlite3.OperationalError:
                pass  # Colonna già presente
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
def insertDialog(ID, chat) -> bool:
    startDB()
    global connection
    result = connection.execute(
        "INSERT OR IGNORE INTO DIALOGS(ID_UTENTE, TYPE, DIALOG_ID, DIALOG_NAME) VALUES (?, ?, ?, ?)",
        (ID, chat["tipo"], chat["id"], chat["nome"])
    )
    connection.commit()
    return result.rowcount > 0  # True = riga nuova, False = già esisteva


def getActiveDialogs(usr: User) -> list[dict]:
    startDB()
    global connection
    rows = connection.execute(
        "SELECT ID, DIALOG_ID, DIALOG_NAME, TYPE, SIGNAL_PATTERN, MT5_ACCOUNT_ID FROM DIALOGS "
        "WHERE ID_UTENTE = ? AND IS_ACTIVE = 1",
        (usr.ID,)
    ).fetchall()
    return [
        {"pk": r[0], "dialog_id": r[1], "nome": r[2], "tipo": r[3],
         "pattern": r[4], "mt5_account_id": r[5]}
        for r in rows
    ]


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


def getMT5Accounts(usr: User, account_id: int | None = None) -> list[dict]:
    """
    Ritorna gli account MT5 dell'utente.
    Se account_id è specificato, ritorna solo quell'account (lista con 0 o 1 elemento).
    Campi: id, login, password, server, label, lot_size
    """
    startDB()
    global connection
    if account_id is not None:
        rows = connection.execute(
            "SELECT ID, LOGIN, PASSWORD, SERVER, LABEL, LOT_SIZE FROM MT5_ACCOUNTS "
            "WHERE ID_UTENTE = ? AND ID = ?",
            (usr.ID, account_id)
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT ID, LOGIN, PASSWORD, SERVER, LABEL, LOT_SIZE FROM MT5_ACCOUNTS "
            "WHERE ID_UTENTE = ?",
            (usr.ID,)
        ).fetchall()
    return [
        {"id": r[0], "login": r[1], "password": r[2],
         "server": r[3], "label": r[4], "lot_size": r[5]}
        for r in rows
    ]


def getSymbols(usr: User, mt5_account_id: int | None = None) -> dict[str, str]:
    """
    Ritorna {SYMBOL_TG: SYMBOL_MT5} per l'utente dato.
    Se mt5_account_id è specificato, filtra per quell'account MT5.
    Chiavi sempre in maiuscolo per confronti case-insensitive.
    """
    startDB()
    global connection
    if mt5_account_id is not None:
        rows = connection.execute(
            "SELECT SYMBOL_TG, SYMBOL_MT5 FROM SYMBOLS "
            "WHERE ID_UTENTE = ? AND MT5_ACCOUNT_ID = ?",
            (usr.ID, mt5_account_id)
        ).fetchall()
    else:
        rows = connection.execute(
            "SELECT SYMBOL_TG, SYMBOL_MT5 FROM SYMBOLS WHERE ID_UTENTE = ?",
            (usr.ID,)
        ).fetchall()
    return {r[0].upper(): r[1] for r in rows}


def saveSignal(usr: User, dialog_id: str, sender_id: str | None, signal) -> int:
    """Salva un segnale e i suoi TP. Ritorna l'ID del segnale inserito."""
    startDB()
    global connection
    cursor = connection.execute(
        "INSERT INTO SIGNALS(ID_UTENTE, DIALOG_ID, SENDER_ID, SYMBOL, ACTION, "
        "ENTRY, SL, RAW_TEXT, RECEIVED_AT) VALUES (?,?,?,?,?,?,?,?,?)",
        (usr.ID, dialog_id, sender_id, signal.symbol, signal.action,
         signal.entry, signal.sl, signal.raw_text, datetime.now().isoformat())
    )
    signal_id = cursor.lastrowid
    for i, price in enumerate(signal.tp, start=1):
        connection.execute(
            "INSERT INTO SIGNAL_TP(SIGNAL_ID, LEVEL, PRICE) VALUES (?,?,?)",
            (signal_id, i, price)
        )
    connection.commit()
    return signal_id
