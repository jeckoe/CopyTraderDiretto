# Project Task Tracker

## TODO

- [ ] Ricreare tests.py (file mancante dal filesystem — 16 test documentati in PROJECT_STATE.md)
- [ ] TODO 2: `getSymbols()` in gestoreDB.py
- [ ] TODO 2: `_find_symbol()` e `_build_symbol_pattern()` in analyzer.py
- [ ] TODO 2: Test 17 (symbol dal DB)
- [ ] Primo commit git (nessun commit presente nel repo)
- [ ] Decidere mapping DIALOG → MT5_ACCOUNT (prerequisito MT5 executor)
- [ ] MT5 executor (`mt5_executor.py`)

## IN_PROGRESS

## DONE

- [x] Keyword parser completo (symbol regex `[A-Z][A-Z0-9]{1,9}`)
- [x] Pattern parser (symbol regex `[A-Z]{2,10}` — da fixare in TODO 2)
- [x] Action types dinamici dal DB (_NON_ACTION_TYPES)
- [x] saveSignal + SIGNALS + SIGNAL_TP nel DB
- [x] MT5_ACCOUNTS e SYMBOLS: tabelle create nel DB
- [x] Tutte le funzioni gestoreDB.py (tranne getSymbols)
- [x] Virtual environment `.venv` creato (Python 3.13.2)
- [x] requirements.txt creato (pyrogram 2.0.106, tenacity 9.0.0)
- [x] DB inizializzato — 11 tabelle create correttamente

## BLOCKED

- [ ] MT5 executor — bloccato su decisione mapping DIALOG→MT5_ACCOUNT
