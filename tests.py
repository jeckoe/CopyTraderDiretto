import gestoreDB
import analyzer
from User import User

TEST_USERNAME = "test_copytrade_auto"
TEST_PASSWORD = "test123"
TEST_CHAT_ID  = "88888888"
TEST_DIALOG_PK = 8888


# ──────────────────────────────────────────────
# Setup / Teardown
# ──────────────────────────────────────────────

def setup_keywords() -> User:
    """Registra l'utente test e inserisce le keyword globali di base."""
    gestoreDB.startDB()

    # Recupera o registra l'utente test
    try:
        usr = gestoreDB.registerUser(TEST_USERNAME, TEST_PASSWORD)
    except ValueError:
        usr = gestoreDB.getUser(TEST_USERNAME, TEST_PASSWORD)

    # Keyword globali (DIALOG_ID = NULL)
    base_keywords = [
        (usr.ID, None, "BUY",   "buy"),
        (usr.ID, None, "BUY",   "long"),
        (usr.ID, None, "SELL",  "sell"),
        (usr.ID, None, "SELL",  "short"),
        (usr.ID, None, "ENTRY", "entry"),
        (usr.ID, None, "SL",    "sl"),
        (usr.ID, None, "SL",    "stop loss"),
        (usr.ID, None, "TP",    "tp"),
    ]
    for row in base_keywords:
        gestoreDB.connection.execute(
            "INSERT INTO SIGNAL_KEYWORDS(ID_UTENTE, DIALOG_ID, KEYWORD_TYPE, KEYWORD) VALUES (?,?,?,?)",
            row
        )
    gestoreDB.connection.commit()

    # Imposta _active_dialogs direttamente senza passare dal DB
    analyzer._active_dialogs = {
        TEST_CHAT_ID: {
            "pk": TEST_DIALOG_PK,
            "dialog_id": TEST_CHAT_ID,
            "nome": "Test Dialog",
            "tipo": "GROUP",
            "pattern": None
        }
    }
    return usr


def teardown_keywords(usr: User) -> None:
    """Cancella tutti i dati dell'utente test dal DB."""
    gestoreDB.startDB()
    gestoreDB.connection.execute("DELETE FROM SIGNAL_KEYWORDS      WHERE ID_UTENTE = ?", (usr.ID,))
    gestoreDB.connection.execute("DELETE FROM SKIP_KEYWORDS        WHERE ID_UTENTE = ?", (usr.ID,))
    gestoreDB.connection.execute("DELETE FROM SIGNALS              WHERE ID_UTENTE = ?", (usr.ID,))
    gestoreDB.connection.execute("DELETE FROM UNRECOGNIZED_MESSAGES WHERE ID_UTENTE = ?", (usr.ID,))
    gestoreDB.connection.execute("DELETE FROM USERS                WHERE ID_UTENTE = ?", (usr.ID,))
    gestoreDB.connection.commit()
    analyzer._active_dialogs = {}


# ──────────────────────────────────────────────
# Helper runner
# ──────────────────────────────────────────────

def run_test(n: int, description: str, fn) -> bool:
    try:
        fn()
        print(f"[TEST {n:2d}] {description:<55} → PASS")
        return True
    except Exception as e:
        print(f"[TEST {n:2d}] {description:<55} → FAIL: {e}")
        return False


# ──────────────────────────────────────────────
# Helper: reset dialog pattern
# ──────────────────────────────────────────────

def _reset_pattern(pattern=None):
    analyzer._active_dialogs[TEST_CHAT_ID]["pattern"] = pattern


# ──────────────────────────────────────────────
# Test 1 — Keyword parser: segnale completo
# ──────────────────────────────────────────────

def test_1(usr: User):
    _reset_pattern(None)
    text = "EURUSD buy\nentry 1.1234\nsl 1.1200\ntp 1.1250/1.1270/1.1300"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,       f"signal è None"
    assert signal.symbol == "EURUSD", f"symbol={signal.symbol}"
    assert signal.action == "BUY",    f"action={signal.action}"
    assert signal.entry == 1.1234,    f"entry={signal.entry}"
    assert signal.sl == 1.12,         f"sl={signal.sl}"
    assert len(signal.tp) == 3,       f"len(tp)={len(signal.tp)}"
    assert signal.tp[0] == 1.125,     f"tp[0]={signal.tp[0]}"


# ──────────────────────────────────────────────
# Test 2 — Keyword parser: minimi (symbol + action)
# ──────────────────────────────────────────────

def test_2(usr: User):
    _reset_pattern(None)
    text = "EURUSD buy"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,       f"signal è None"
    assert signal.symbol == "EURUSD", f"symbol={signal.symbol}"
    assert signal.action == "BUY",    f"action={signal.action}"
    assert signal.entry is None,      f"entry={signal.entry}"
    assert signal.sl is None,         f"sl={signal.sl}"
    assert signal.tp == [],           f"tp={signal.tp}"


# ──────────────────────────────────────────────
# Test 3 — Keyword parser: messaggio non valido
# ──────────────────────────────────────────────

def test_3(usr: User):
    _reset_pattern(None)
    text = "ciao come stai"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is None, f"signal non è None: {signal}"


# ──────────────────────────────────────────────
# Test 4 — Keyword parser: TP multipli sulla stessa riga con /
# ──────────────────────────────────────────────

def test_4(usr: User):
    _reset_pattern(None)
    text = "EURUSD buy\ntp 1.1250/1.1270/1.1300"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,              f"signal è None"
    assert len(signal.tp) == 3,             f"len(tp)={len(signal.tp)}"
    assert signal.tp == [1.125, 1.127, 1.13], f"tp={signal.tp}"


# ──────────────────────────────────────────────
# Test 5 — Keyword parser: TP multipli su righe separate
# ──────────────────────────────────────────────

def test_5(usr: User):
    _reset_pattern(None)
    text = "EURUSD buy\ntp 1.1250\ntp 1.1270\ntp 1.1300"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,              f"signal è None"
    assert len(signal.tp) == 3,             f"len(tp)={len(signal.tp)}"
    assert signal.tp == [1.125, 1.127, 1.13], f"tp={signal.tp}"


# ──────────────────────────────────────────────
# Test 6 — Keyword parser: symbol non confuso con keyword
# ──────────────────────────────────────────────

def test_6(usr: User):
    _reset_pattern(None)
    text = "EURUSD sell\nsl 1.1200"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,        f"signal è None"
    assert signal.symbol == "EURUSD", f"symbol={signal.symbol}"
    assert signal.action == "SELL",   f"action={signal.action}"


# ──────────────────────────────────────────────
# Test 7 — Keyword parser: action type custom (dinamico dal DB)
# ──────────────────────────────────────────────

def test_7(usr: User):
    _reset_pattern(None)
    gestoreDB.connection.execute(
        "INSERT INTO SIGNAL_KEYWORDS(ID_UTENTE, DIALOG_ID, KEYWORD_TYPE, KEYWORD) VALUES (?,?,?,?)",
        (usr.ID, None, "SCALP", "scalp")
    )
    gestoreDB.connection.commit()
    text = "BTCUSD scalp\nentry 50000"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,       f"signal è None"
    assert signal.action == "SCALP", f"action={signal.action}"


# ──────────────────────────────────────────────
# Test 8 — Pattern parser: riga singola
# ──────────────────────────────────────────────

def test_8(usr: User):
    _reset_pattern("{SYMBOL} {ACTION} {ENTRY} {SL} {TP}")
    text = "EURUSD BUY 1.1234 1.1200 1.1250"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,        f"signal è None"
    assert signal.symbol == "EURUSD", f"symbol={signal.symbol}"
    assert signal.action == "BUY",    f"action={signal.action}"
    assert signal.entry == 1.1234,    f"entry={signal.entry}"
    assert signal.sl == 1.12,         f"sl={signal.sl}"
    assert signal.tp == [1.125],      f"tp={signal.tp}"


# ──────────────────────────────────────────────
# Test 9 — Pattern parser: multiriga con 3 TP
# ──────────────────────────────────────────────

def test_9(usr: User):
    _reset_pattern("{SYMBOL}\n{ACTION}\nentry {ENTRY}\nsl {SL}\ntp1 {TP}\ntp2 {TP}\ntp3 {TP}")
    text = "EURUSD\nBUY\nentry 1.1234\nsl 1.1200\ntp1 1.1250\ntp2 1.1270\ntp3 1.1300"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,  f"signal è None"
    assert len(signal.tp) == 3, f"len(tp)={len(signal.tp)}"


# ──────────────────────────────────────────────
# Test 10 — Pattern parser: spazi multipli / newline (XAUUSD)
# ──────────────────────────────────────────────

def test_10(usr: User):
    _reset_pattern("{SYMBOL} {ACTION} {ENTRY}")
    text = "XAUUSD   BUY   2300"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,        f"signal è None"
    assert signal.symbol == "XAUUSD", f"symbol={signal.symbol}"
    assert signal.entry == 2300.0,    f"entry={signal.entry}"


# ──────────────────────────────────────────────
# Test 11 — Pattern parser: keyword personalizzata (Vendi → SELL)
# ──────────────────────────────────────────────

def test_11(usr: User):
    gestoreDB.connection.execute(
        "INSERT INTO SIGNAL_KEYWORDS(ID_UTENTE, DIALOG_ID, KEYWORD_TYPE, KEYWORD) VALUES (?,?,?,?)",
        (usr.ID, None, "SELL", "vendi")
    )
    gestoreDB.connection.execute(
        "INSERT INTO SIGNAL_KEYWORDS(ID_UTENTE, DIALOG_ID, KEYWORD_TYPE, KEYWORD) VALUES (?,?,?,?)",
        (usr.ID, None, "BUY", "compra")
    )
    gestoreDB.connection.commit()
    _reset_pattern("{SYMBOL} {ACTION} {ENTRY}")
    text = "EURUSD Vendi 1.1234"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,      f"signal è None"
    assert signal.action == "SELL", f"action={signal.action}"


# ──────────────────────────────────────────────
# Test 12 — Pattern parser: pattern non matchante → None
# ──────────────────────────────────────────────

def test_12(usr: User):
    _reset_pattern("{SYMBOL} {ACTION} {ENTRY} {SL}")
    pattern = "{SYMBOL} {ACTION} {ENTRY} {SL}"
    dialog_pk = TEST_DIALOG_PK
    text = "questo non matcha nulla"
    result = analyzer._parse_with_pattern(text, pattern, TEST_CHAT_ID, usr, dialog_pk)
    assert result is None, f"result non è None: {result}"


# ──────────────────────────────────────────────
# Test 13 — Pattern parser: nessuna keyword → None
# ──────────────────────────────────────────────

def test_13(usr: User):
    gestoreDB.connection.execute(
        "DELETE FROM SIGNAL_KEYWORDS WHERE ID_UTENTE = ?", (usr.ID,)
    )
    gestoreDB.connection.commit()
    _reset_pattern("{SYMBOL} {ACTION} {ENTRY}")
    pattern = "{SYMBOL} {ACTION} {ENTRY}"
    dialog_pk = TEST_DIALOG_PK
    text = "EURUSD BUY 1.1234"
    result = analyzer._parse_with_pattern(text, pattern, TEST_CHAT_ID, usr, dialog_pk)
    assert result is None, f"result non è None: {result}"


# ──────────────────────────────────────────────
# Test 14 — Keyword parser: compound keyword (buy limit)
# ──────────────────────────────────────────────

def test_14(usr: User):
    gestoreDB.connection.execute(
        "INSERT INTO SIGNAL_KEYWORDS(ID_UTENTE, DIALOG_ID, KEYWORD_TYPE, KEYWORD) VALUES (?,?,?,?)",
        (usr.ID, None, "BUY_LIMIT", "buy limit")
    )
    gestoreDB.connection.commit()
    _reset_pattern(None)
    text = "EURUSD buy limit 1.1234"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,           f"signal è None"
    assert signal.action == "BUY_LIMIT", f"action={signal.action}"


# ──────────────────────────────────────────────
# Test 15 — Keyword parser: symbol con numeri (US30)
# ──────────────────────────────────────────────

def test_15(usr: User):
    _reset_pattern(None)
    text = "US30 buy\nentry 33000\nsl 32900"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,     f"signal è None"
    assert signal.symbol == "US30", f"symbol={signal.symbol}"


# ──────────────────────────────────────────────
# Test 16 — Pattern parser: placeholder {IGNORE}
# ──────────────────────────────────────────────

def test_16(usr: User):
    _reset_pattern("{IGNORE}\n{SYMBOL} {ACTION} {ENTRY}")
    text = "Segnale importante da non considerare!\nEURUSD BUY 1.1234"
    signal = analyzer.analyze(usr, TEST_CHAT_ID, None, text)
    assert signal is not None,        f"signal è None"
    assert signal.symbol == "EURUSD", f"symbol={signal.symbol}"
    assert signal.action == "BUY",    f"action={signal.action}"
    assert signal.entry == 1.1234,    f"entry={signal.entry}"


# ──────────────────────────────────────────────
# Runner principale
# ──────────────────────────────────────────────

def run_all_tests():
    usr = setup_keywords()
    try:
        risultati = []
        risultati.append(run_test(1,  "Keyword parser: segnale completo",              lambda: test_1(usr)))
        risultati.append(run_test(2,  "Keyword parser: minimi (symbol+action)",         lambda: test_2(usr)))
        risultati.append(run_test(3,  "Keyword parser: messaggio non valido",           lambda: test_3(usr)))
        risultati.append(run_test(4,  "Keyword parser: TP multipli sulla stessa riga",  lambda: test_4(usr)))
        risultati.append(run_test(5,  "Keyword parser: TP multipli su righe separate",  lambda: test_5(usr)))
        risultati.append(run_test(6,  "Keyword parser: symbol non confuso con keyword", lambda: test_6(usr)))
        risultati.append(run_test(7,  "Keyword parser: action type custom (SCALP)",     lambda: test_7(usr)))
        risultati.append(run_test(8,  "Pattern parser: riga singola",                   lambda: test_8(usr)))
        risultati.append(run_test(9,  "Pattern parser: multiriga con 3 TP",             lambda: test_9(usr)))
        risultati.append(run_test(10, "Pattern parser: spazi multipli/newline (XAUUSD)",lambda: test_10(usr)))
        risultati.append(run_test(11, "Pattern parser: keyword personalizzata Vendi",   lambda: test_11(usr)))
        risultati.append(run_test(12, "Pattern parser: pattern non matchante → None",   lambda: test_12(usr)))
        risultati.append(run_test(13, "Pattern parser: nessuna keyword → None",          lambda: test_13(usr)))

        # Test 13 ha cancellato tutte le keyword — ripristina
        usr2 = setup_keywords()

        risultati.append(run_test(14, "Keyword parser: compound keyword (buy limit)",   lambda: test_14(usr2)))
        risultati.append(run_test(15, "Keyword parser: symbol con numeri (US30)",       lambda: test_15(usr2)))
        risultati.append(run_test(16, "Pattern parser: placeholder {IGNORE}",           lambda: test_16(usr2)))

    finally:
        teardown_keywords(usr)

    passati = sum(risultati)
    print(f"\n{'='*40}")
    print(f"Risultato: {passati}/16 test passati")


if __name__ == "__main__":
    run_all_tests()
