# PROJECT_STATE.md — Stato verificato sui sorgenti reali

## Ultimo commit
```
feat: analyzer hardening + bug fix + test suite completa

- Fix compound keyword: ricerca azione ordinata per lunghezza decrescente
- Fix symbol con numeri nel keyword parser: [A-Z][A-Z0-9]{1,9}
- Fix {IGNORE} nel pattern: greedy .* invece di lazy .*?
- Fix whitespace pattern: replace('\\ ', \s+) e replace('\\\n', \s+)
- TODO 1: action types dinamici dal DB via _NON_ACTION_TYPES
- saveSignal + SIGNALS + SIGNAL_TP nel DB
- MT5_ACCOUNTS e SYMBOLS: tabelle create nel DB
- tests.py: 16 test tutti ✅
```

---

## Stato reale per file

### analyzer.py
| Funzione | Stato |
|----------|-------|
| `load_active_dialogs` | ✅ completo |
| `analyze` | ✅ completo |
| `_parse_with_keywords` | ✅ completo — symbol regex `[A-Z][A-Z0-9]{1,9}` |
| `_parse_with_pattern` | ⚠️ symbol regex ancora `[A-Z]{2,10}` — TODO 2 |
| `_resolve_action` | ✅ completo |
| `_contains_skip` | ✅ completo |
| `_extract_first_number` | ✅ completo |
| `_extract_all_numbers` | ✅ completo |
| `_find_symbol` | ❌ non ancora creata — TODO 2 |
| `_build_symbol_pattern` | ❌ non ancora creata — TODO 2 |

### gestoreDB.py
| Funzione | Stato |
|----------|-------|
| `startDB` | ✅ |
| `getUser` | ✅ |
| `getTelegramConfig` | ✅ |
| `saveSession` | ✅ |
| `insertDialog` | ✅ — ritorna bool (True=nuovo) |
| `getActiveDialogs` | ✅ — include SIGNAL_PATTERN |
| `getSignalKeywords` | ✅ — logica gerarchica globali+specifiche |
| `getSkipKeywords` | ✅ — logica gerarchica globali+specifiche |
| `saveUnrecognized` | ✅ |
| `registerUser` | ✅ |
| `saveTelegramConfig` | ✅ |
| `saveLog` | ✅ |
| `usernameExists` | ✅ |
| `saveSignal` | ✅ — salva SIGNALS + SIGNAL_TP |
| `getSymbols` | ❌ non ancora creata — TODO 2 |

### tests.py
| Test | Cosa testa | Stato |
|------|-----------|-------|
| 1 | Keyword parser segnale completo | ✅ |
| 2 | Keyword parser minimi (symbol+action) | ✅ |
| 3 | Keyword parser messaggio non valido | ✅ |
| 4 | Keyword parser TP multipli stessa riga `/` | ✅ |
| 5 | Keyword parser TP multipli righe separate | ✅ |
| 6 | Keyword parser symbol non confuso con keyword | ✅ |
| 7 | Keyword parser action type custom (TODO 1) | ✅ |
| 8 | Pattern parser riga singola | ✅ |
| 9 | Pattern parser multiriga 3 TP | ✅ |
| 10 | Pattern parser spazi multipli/newline (XAUUSD) | ✅ |
| 11 | Pattern parser keyword personalizzata (Vendi→SELL) | ✅ |
| 12 | Pattern parser non matchante | ✅ |
| 13 | Pattern parser nessuna keyword → None | ✅ |
| 14 | Keyword parser compound keyword (buy limit) | ✅ |
| 15 | Keyword parser symbol con numeri (US30) | ✅ |
| 16 | Pattern parser placeholder {IGNORE} | ✅ |
| 17 | Symbol dal DB (TODO 2) | ❌ non ancora scritto |

---

## Bug noti aperti

| Bug | File | Descrizione |
|-----|------|-------------|
| Symbol con numeri nel pattern parser | `analyzer.py` | `{SYMBOL}` usa `[A-Z]{2,10}`, non supporta US30/NAS100. Fix in TODO 2. |

---

## Prossimi step in ordine

1. **Sessione apprendimento Python** — richiesta da Andrea sul codice esistente
2. **TODO 2** — symbol dal DB in entrambi i parser + test 17
3. **MT5 executor** — decidere prima mapping DIALOG→MT5_ACCOUNT
