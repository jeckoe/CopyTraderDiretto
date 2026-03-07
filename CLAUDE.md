# CopyTraderDiretto — Contesto per Claude Code

## Cos'è questo progetto
Sistema Python che legge messaggi da canali Telegram, li analizza alla ricerca
di segnali di trading, e li esegue su MetaTrader 5. Sviluppato insieme ad Andrea
(utente non esperto Python, preferisce spiegazioni chiare e codice modulare).

---

## Struttura file

```
CopyTraderDiretto/
├── main.py           # Entrypoint: login, scan dialog, avvio listener
├── client.py         # Connessione Telegram con retry (tenacity)
├── listener.py       # Pyrogram MessageHandler → chiama analyzer → saveSignal
├── analyzer.py       # Parser segnali: keyword parser + pattern parser
├── signal_model.py   # Dataclass Signal
├── scanner.py        # Scansione dialog Telegram → salvataggio DB
├── gestoreDB.py      # Tutte le funzioni SQLite
├── User.py           # Classe utente
├── tests.py          # Suite 16 test con setup/teardown DB
└── diretto.db        # Database SQLite
```

---

## Schema DB completo

```sql
USERS           (ID_UTENTE, USERNAME, PASSWORD)
TCONFIG         (API_ID, API_HASH, TEL_NUMBER, SESSION_NAME, ID_UTENTE, SESSION_STRING)
DIALOGS         (ID, ID_UTENTE, TYPE, DIALOG_ID, DIALOG_NAME, IS_ACTIVE, SIGNAL_PATTERN)
SIGNAL_KEYWORDS (ID, ID_UTENTE, DIALOG_ID, KEYWORD_TYPE, KEYWORD)
SKIP_KEYWORDS   (ID, ID_UTENTE, DIALOG_ID, KEYWORD)
SIGNALS         (ID, ID_UTENTE, DIALOG_ID, SENDER_ID, SYMBOL, ACTION, ENTRY, SL, RAW_TEXT, RECEIVED_AT)
SIGNAL_TP       (ID, SIGNAL_ID, LEVEL, PRICE)
UNRECOGNIZED_MESSAGES (ID, ID_UTENTE, DIALOG_ID, SENDER_ID, RAW_TEXT, RECEIVED_AT)
LOGS            (ID, ID_UTENTE, SESSION_ID, LEVEL, MODULE, MESSAGE, CREATED_AT)
MT5_ACCOUNTS    (ID, ID_UTENTE, LOGIN, PASSWORD, SERVER, LABEL)
SYMBOLS         (ID, ID_UTENTE, MT5_ACCOUNT_ID, SYMBOL_TG, SYMBOL_MT5)
```

**Regole importanti:**
- `SIGNAL_KEYWORDS.DIALOG_ID = NULL` → keyword globale (vale per tutti i canali)
- `SIGNAL_KEYWORDS.DIALOG_ID = X` → keyword specifica per quel canale (si aggiunge alle globali)
- Stessa logica per `SKIP_KEYWORDS`
- `DIALOGS.IS_ACTIVE = 1` → il canale viene analizzato
- `DIALOGS.SIGNAL_PATTERN` → pattern opzionale, NULL = usa keyword parser
- `SYMBOLS.SYMBOL_TG` → come arriva da Telegram (es. "GOLD")
- `SYMBOLS.SYMBOL_MT5` → come vuole il broker MT5 (es. "XAUUSD.")

---

## Architettura analyzer.py (stato reale)

**Due parser:**

1. **Keyword parser** (`_parse_with_keywords`) — scansiona riga per riga cercando
   keyword configurate nel DB. Nessuna dipendenza dalla posizione nel messaggio.
   - Symbol regex: `[A-Z][A-Z0-9]{1,9}` → supporta US30, NAS100, XAUUSD ✅

2. **Pattern parser** (`_parse_with_pattern`) — usa template con placeholder fissi:
   `{SYMBOL}`, `{ACTION}`, `{ENTRY}`, `{SL}`, `{TP}`, `{IGNORE}`
   - Symbol regex: `[A-Z]{2,10}` → NON supporta US30/NAS100 ⚠️ (TODO 2)

**Flusso decide quale usare:**
```
SIGNAL_PATTERN != NULL → prova pattern → se fallisce → keyword parser (fallback)
SIGNAL_PATTERN == NULL → keyword parser direttamente
```

**`_NON_ACTION_TYPES = {"ENTRY", "SL", "TP", "CLOSE", "IGNORE"}`**
Tutto ciò che NON è in questo set viene trattato come action type.
Questo rende i tipi di azione completamente dinamici dal DB (TODO 1 ✅).

**Keyword ordinate per lunghezza decrescente:** sia nel keyword parser che nel pattern
parser, per garantire che "buy limit" venga trovato prima di "buy".

**Fix whitespace pattern (critico):**
```python
regex = re.escape(pattern)
regex = regex.replace('\\ ', r'\s+')   # spazio escaped → \s+
regex = regex.replace('\\\n', r'\s+')  # newline escaped → \s+
```
Questo fix è necessario perché `re.escape` trasforma spazi in `\ ` e newline
in `\` + newline letterale (non `\n` come stringa).

---

## TODO aperti

### TODO 2 — Symbol dal DB (prossimo step, non ancora implementato)

**Problema attuale:** `{SYMBOL}` nel pattern parser usa regex hardcoded
`[A-Z]{2,10}` che non supporta simboli con numeri (US30, NAS100).
Il keyword parser è già stato fixato ma il pattern parser no.

**Soluzione progettata — aggiungere in `gestoreDB.py`:**
```python
def getSymbols(usr: User, mt5_account_id: int | None = None) -> dict[str, str]:
    # Ritorna {SYMBOL_TG: SYMBOL_MT5}
    # Filtra per mt5_account_id se specificato
```

**Aggiungere in `analyzer.py`:**
```python
def _find_symbol(line_upper, keywords, usr) -> str | None:
    # 1. Cerca prima tra SYMBOLS configurati nel DB (più preciso)
    # 2. Fallback: regex generica [A-Z][A-Z0-9]{1,9}

def _build_symbol_pattern(usr) -> str:
    # Costruisce regex per {SYMBOL} dai symbol del DB
    # Fallback se nessun symbol configurato: r"(?P<SYMBOL>[A-Z][A-Z0-9]{1,9})"
```

**Sostituire in `_parse_with_keywords`:**
```python
# Vecchio codice inline
match = re.search(r'\b[A-Z][A-Z0-9]{1,9}\b', line.upper())
# → chiamare _find_symbol(line.upper(), keywords, usr)
```

**Sostituire in `_parse_with_pattern` placeholders:**
```python
"{SYMBOL}": r"(?P<SYMBOL>[A-Z]{2,10})",   # vecchio
"{SYMBOL}": _build_symbol_pattern(usr),    # nuovo
```

**Test 17** da aggiungere in `tests.py` (già progettato):
```python
# Inserisce MT5_ACCOUNTS e SYMBOLS temporanei
# Verifica che "GOLD" venga trovato tramite DB
# Cleanup nel finally
```

---

## MT5 Executor (step principale successivo)

**File da creare:** `mt5_executor.py`
- Libreria: `MetaTrader5` (solo Windows con MT5 installato)
- Dati connessione da `MT5_ACCOUNTS`
- Mapping symbol: `SYMBOLS.SYMBOL_TG → SYMBOLS.SYMBOL_MT5`

**Domande aperte da decidere prima di implementare:**
1. Un segnale va su tutti gli account MT5 dell'utente o solo uno specifico?
   (probabilmente serve mappatura DIALOG → MT5_ACCOUNT)
2. `IS_HIT` su `SIGNAL_TP`: aggiornato dall'executor quando il prezzo viene raggiunto?

---

## Convenzioni del progetto

**Logging:**
- Moduli salvati nel DB: `{"__main__", "analyzer", "listener", "client", "scanner"}`
- Warning/Error/Critical salvati sempre
- Prefissi log: `[LISTENER]`, `[SIGNAL]`, `[ANALYZER]`, `[SCANNER]`

**gestoreDB.py:**
- Connessione globale singola (`connection`, `isDBStarted`)
- Ogni funzione chiama `startDB()` prima di usare `connection`
- `INSERT OR IGNORE` dove c'è UNIQUE constraint
- `result.rowcount` per verificare effetto di UPDATE/INSERT

**Pyrogram:**
- `in_memory=True` — nessun file .session su disco
- `session_string` salvata nel DB dopo ogni login riuscito
- `idle()` standalone (non `app.idle()`)
- Closure `build_message_handler(usr)` per passare `usr` al callback senza
  modificare la firma che Pyrogram si aspetta

**tests.py:**
- `setup_keywords()` / `teardown_keywords()` — autonomo, non dipende da dati reali
- `try/finally` garantisce cleanup anche in caso di crash
- Test 13 cancella tutte le keyword → `setup_keywords()` chiamato di nuovo
  prima di test 14-16 (già presente in `run_all_tests()`)
- Test 17 (TODO 2) non ancora nel file reale

---

## Stile comunicazione con Andrea

- Non esperto Python — spiegare i concetti quando si introducono
- Un file / un concetto alla volta, chiedere conferma prima di procedere
- Accetta critiche costruttive, non vuole yes-man
- Commit message dettagliati in italiano
- Ha richiesto una sessione di apprendimento Python sul codice esistente
  prima di procedere con MT5
