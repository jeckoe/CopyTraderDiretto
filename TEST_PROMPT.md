# Prompt — CopyTraderDiretto Test Suite Runner

## Contesto
Sei un agente QA per il progetto **CopyTraderDiretto**.
Directory di lavoro: `C:\Users\viana\Desktop\CopyTraderDiretto\CopyTraderDiretto-master`
Python interpreter da usare: `.venv\Scripts\python`

Prima di scrivere qualsiasi cosa, leggi i seguenti file sorgente:
- `analyzer.py`
- `gestoreDB.py`
- `User.py`
- `signal_model.py`

---

## Il tuo compito

1. **Crea** il file `tests.py` nella cartella del progetto seguendo ESATTAMENTE le specifiche qui sotto
2. **Esegui** `tests.py` con il venv del progetto
3. **Riporta** pass/fail per ogni test con dettaglio sugli errori

---

## Struttura di tests.py

### Import e costanti

```python
import gestoreDB
import analyzer
from User import User

TEST_USERNAME = "test_copytrade_auto"
TEST_PASSWORD = "test123"
TEST_CHAT_ID  = "88888888"
TEST_DIALOG_PK = 8888
```

---

### `setup_keywords()`

Funzione che:
1. Registra l'utente test nel DB (se esiste già, lo recupera con `getUser`)
2. Inserisce queste keyword globali (DIALOG_ID = NULL) per quell'utente:

   | KEYWORD_TYPE | KEYWORD     |
   |-------------|-------------|
   | BUY         | buy         |
   | BUY         | long        |
   | SELL        | sell        |
   | SELL        | short       |
   | ENTRY       | entry       |
   | SL          | sl          |
   | SL          | stop loss   |
   | TP          | tp          |

3. Imposta `analyzer._active_dialogs` direttamente (senza passare dal DB):
   ```python
   analyzer._active_dialogs = {
       TEST_CHAT_ID: {
           "pk": TEST_DIALOG_PK,
           "dialog_id": TEST_CHAT_ID,
           "nome": "Test Dialog",
           "tipo": "GROUP",
           "pattern": None
       }
   }
   ```
4. Ritorna l'oggetto `usr`

---

### `teardown_keywords(usr)`

Funzione che cancella **tutto** ciò che riguarda l'utente test:
- `SIGNAL_KEYWORDS` dove `ID_UTENTE = usr.ID`
- `SKIP_KEYWORDS` dove `ID_UTENTE = usr.ID`
- `SIGNALS` dove `ID_UTENTE = usr.ID`
- `UNRECOGNIZED_MESSAGES` dove `ID_UTENTE = usr.ID`
- `USERS` dove `ID_UTENTE = usr.ID`

Poi resetta `analyzer._active_dialogs = {}`.
Chiama sempre `gestoreDB.connection.commit()` alla fine.

---

### Helper `run_test(n, description, fn)`

Esegue `fn()`, stampa `[TEST n] description → PASS` oppure `FAIL: <errore>`.
Ritorna `True` se PASS, `False` se FAIL.

---

### `run_all_tests()`

Struttura con `try/finally`:

```python
usr = setup_keywords()
try:
    risultati = []
    risultati.append(run_test(1,  "...", lambda: test_1(usr)))
    # ... tutti i 16 test ...
finally:
    teardown_keywords(usr)

passati = sum(risultati)
print(f"\n{'='*40}")
print(f"Risultato: {passati}/16 test passati")
```

**Attenzione:** il Test 13 cancella tutte le keyword. Prima del Test 14,
chiama `setup_keywords()` di nuovo assegnando il risultato a `usr`.

---

## I 16 test da implementare

Per ogni test: usa `analyze(usr, TEST_CHAT_ID, None, text)` a meno che non sia
indicato diversamente. Resetta `analyzer._active_dialogs[TEST_CHAT_ID]["pattern"] = None`
all'inizio di ogni test (keyword parser) e impostalo al valore corretto per i test
del pattern parser.

---

### Test 1 — Keyword parser: segnale completo

```
EURUSD buy
entry 1.1234
sl 1.1200
tp 1.1250/1.1270/1.1300
```

Verifica: `signal is not None`, `symbol=="EURUSD"`, `action=="BUY"`,
`entry==1.1234`, `sl==1.12`, `len(tp)==3`, `tp[0]==1.125`

---

### Test 2 — Keyword parser: minimi (symbol + action)

```
EURUSD buy
```

Verifica: `signal is not None`, `symbol=="EURUSD"`, `action=="BUY"`,
`entry is None`, `sl is None`, `tp==[]`

---

### Test 3 — Keyword parser: messaggio non valido

```
ciao come stai
```

Verifica: `signal is None`

---

### Test 4 — Keyword parser: TP multipli sulla stessa riga con `/`

```
EURUSD buy
tp 1.1250/1.1270/1.1300
```

Verifica: `len(tp)==3`, `tp==[1.125, 1.127, 1.13]`

---

### Test 5 — Keyword parser: TP multipli su righe separate

```
EURUSD buy
tp 1.1250
tp 1.1270
tp 1.1300
```

Verifica: `len(tp)==3`, `tp==[1.125, 1.127, 1.13]`

---

### Test 6 — Keyword parser: symbol non confuso con keyword

```
EURUSD sell
sl 1.1200
```

Verifica: `symbol=="EURUSD"` (non "SELL"), `action=="SELL"`

---

### Test 7 — Keyword parser: action type custom (dinamico dal DB)

Prima di chiamare `analyze()`, inserisci nel DB la keyword:
`(usr.ID, None, "SCALP", "scalp")`

```
BTCUSD scalp
entry 50000
```

Verifica: `signal is not None`, `action=="SCALP"`

---

### Test 8 — Pattern parser: riga singola

Imposta `pattern = "{SYMBOL} {ACTION} {ENTRY} {SL} {TP}"`

```
EURUSD BUY 1.1234 1.1200 1.1250
```

Verifica: `signal is not None`, `symbol=="EURUSD"`, `action=="BUY"`,
`entry==1.1234`, `sl==1.12`, `tp==[1.125]`

---

### Test 9 — Pattern parser: multiriga con 3 TP

Imposta:
```
pattern = "{SYMBOL}\n{ACTION}\nentry {ENTRY}\nsl {SL}\ntp1 {TP}\ntp2 {TP}\ntp3 {TP}"
```

```
EURUSD
BUY
entry 1.1234
sl 1.1200
tp1 1.1250
tp2 1.1270
tp3 1.1300
```

Verifica: `signal is not None`, `len(tp)==3`

---

### Test 10 — Pattern parser: spazi multipli / newline (XAUUSD)

Imposta `pattern = "{SYMBOL} {ACTION} {ENTRY}"`

```
XAUUSD   BUY   2300
```
(tre spazi tra i campi)

Verifica: `signal is not None`, `symbol=="XAUUSD"`, `entry==2300.0`

---

### Test 11 — Pattern parser: keyword personalizzata (Vendi → SELL)

Prima del test, inserisci nel DB:
- `(usr.ID, None, "SELL", "vendi")`
- `(usr.ID, None, "BUY",  "compra")`

Imposta `pattern = "{SYMBOL} {ACTION} {ENTRY}"`

```
EURUSD Vendi 1.1234
```

Verifica: `signal is not None`, `action=="SELL"`

---

### Test 12 — Pattern parser: pattern non matchante → None

Imposta `pattern = "{SYMBOL} {ACTION} {ENTRY} {SL}"` (richiede 4 campi)

Chiama **direttamente** `analyzer._parse_with_pattern(...)` (non `analyze`)
con testo:
```
questo non matcha nulla
```

Verifica: `result is None`

---

### Test 13 — Pattern parser: nessuna keyword → None

Cancella **tutte** le keyword dell'utente test:
```python
gestoreDB.connection.execute("DELETE FROM SIGNAL_KEYWORDS WHERE ID_UTENTE = ?", (usr.ID,))
gestoreDB.connection.commit()
```

Imposta `pattern = "{SYMBOL} {ACTION} {ENTRY}"`

Chiama **direttamente** `analyzer._parse_with_pattern(...)` con:
```
EURUSD BUY 1.1234
```

Verifica: `result is None` (senza keyword di azione, il pattern parser torna None)

---

### Test 14 — Keyword parser: compound keyword (buy limit)

*(Questo test viene eseguito dopo aver chiamato di nuovo `setup_keywords()`)*

Prima del test, inserisci nel DB:
- `(usr.ID, None, "BUY_LIMIT", "buy limit")`

Imposta `pattern = None` (keyword parser)

```
EURUSD buy limit 1.1234
```

Verifica: `signal is not None`, `action=="BUY_LIMIT"` (non "BUY")

---

### Test 15 — Keyword parser: symbol con numeri (US30)

Imposta `pattern = None` (keyword parser)

```
US30 buy
entry 33000
sl 32900
```

Verifica: `signal is not None`, `symbol=="US30"`

---

### Test 16 — Pattern parser: placeholder `{IGNORE}`

Imposta `pattern = "{IGNORE}\n{SYMBOL} {ACTION} {ENTRY}"`

```
Segnale importante da non considerare!
EURUSD BUY 1.1234
```

Verifica: `signal is not None`, `symbol=="EURUSD"`, `action=="BUY"`, `entry==1.1234`

---

## Come eseguire

```bash
cd C:\Users\viana\Desktop\CopyTraderDiretto\CopyTraderDiretto-master
.venv\Scripts\python tests.py
```

## Output atteso

```
[TEST  1] Keyword parser: segnale completo           → PASS
[TEST  2] Keyword parser: minimi (symbol+action)     → PASS
...
[TEST 16] Pattern parser: {IGNORE}                   → PASS

========================================
Risultato: 16/16 test passati
```

Se un test fallisce, mostra l'AssertionError o l'eccezione con il valore
effettivo ricevuto per facilitare il debug.
