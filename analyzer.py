import logging
import re

from User import User
from gestoreDB import getActiveDialogs, getSignalKeywords, getSkipKeywords, getSymbols, saveUnrecognized
from signal_model import Signal

logger = logging.getLogger(__name__)
_active_dialogs: dict[str, dict] = {}

# Tipi che NON sono azioni — esclusi quando si cercano le azioni
_NON_ACTION_TYPES = {"ENTRY", "SL", "TP", "CLOSE", "IGNORE"}


def load_active_dialogs(usr: User) -> None:
    global _active_dialogs
    dialogs = getActiveDialogs(usr)
    _active_dialogs = {str(d["dialog_id"]): d for d in dialogs}
    logger.info(f"[ANALYZER] {len(_active_dialogs)} chat attive caricate.")


def analyze(usr: User, chat_id: str, sender_id: str | None, text: str) -> Signal | None:
    if chat_id not in _active_dialogs:
        return None

    dialog = _active_dialogs[chat_id]
    dialog_pk = dialog["pk"]
    text_clean = text.strip()

    skip = getSkipKeywords(usr, dialog_pk)
    if _contains_skip(text_clean, skip):
        logger.info(f"[ANALYZER] Messaggio skippato (skip keyword trovata). chat={chat_id}")
        return None

    pattern = dialog.get("pattern")
    signal = None

    if pattern:
        signal = _parse_with_pattern(text_clean, pattern, chat_id, usr, dialog_pk)
        if signal is None:
            logger.warning(f"[ANALYZER] Pattern non matchato, provo keyword parser. chat={chat_id}")
            signal = _parse_with_keywords(text_clean, usr, dialog_pk, chat_id)
    else:
        signal = _parse_with_keywords(text_clean, usr, dialog_pk, chat_id)

    if signal is None:
        logger.info(f"[ANALYZER] Messaggio non riconosciuto, salvato nel DB. chat={chat_id}")
        saveUnrecognized(usr, chat_id, sender_id, text_clean)

    return signal


# ──────────────────────────────────────────────
# Parser 1 — Keyword (generico, default)
# ──────────────────────────────────────────────
def _parse_with_keywords(text: str, usr: User, dialog_pk: int | None, chat_id: str) -> Signal | None:
    keywords = getSignalKeywords(usr, dialog_pk)
    lines = [l.strip().lower() for l in text.splitlines() if l.strip()]

    symbol = None
    action = None
    entry = None
    sl = None
    tp = []

    for line in lines:
        if action is None:
            action_kw_list = [
                (kw, ktype)
                for ktype in keywords if ktype not in _NON_ACTION_TYPES
                for kw in keywords.get(ktype, [])
            ]
            action_kw_list.sort(key=lambda x: len(x[0]), reverse=True)
            for kw, ktype in action_kw_list:
                if kw in line:
                    action = ktype
                    break

        if symbol is None:
            symbol = _find_symbol(line.upper(), keywords, usr)

        if entry is None and any(kw in line for kw in keywords.get("ENTRY", [])):
            entry = _extract_first_number(line)

        if sl is None and any(kw in line for kw in keywords.get("SL", [])):
            sl = _extract_first_number(line)

        if len(tp) < 3 and any(kw in line for kw in keywords.get("TP", [])):
            numbers = _extract_all_numbers(line)
            for n in numbers:
                if len(tp) < 3:
                    tp.append(n)

    if symbol is None or action is None:
        return None

    return Signal(symbol=symbol, action=action, entry=entry, sl=sl, tp=tp,
                  raw_text=text, source_chat_id=chat_id)


# ──────────────────────────────────────────────
# Parser 2 — Pattern template (specifico per canale)
# ──────────────────────────────────────────────
def _parse_with_pattern(text: str, pattern: str, chat_id: str,
                        usr: User, dialog_pk: int | None) -> Signal | None:
    """
    Usa un template con placeholder fissi per estrarre i campi.
    {ACTION} viene costruito dinamicamente dalle keyword dell'utente,
    quindi supporta keyword personalizzate come "Vendi", "Compra", "Acheter".
    """
    keywords = getSignalKeywords(usr, dialog_pk)

    action_keywords = []
    for ktype in keywords:
        if ktype not in _NON_ACTION_TYPES:
            action_keywords.extend(keywords[ktype])
    action_keywords.sort(key=len, reverse=True)

    if not action_keywords:
        logger.warning(f"[ANALYZER] Nessuna keyword di azione configurata. chat={chat_id}")
        return None

    # Regex per {ACTION} costruita dalle keyword dell'utente
    action_pattern = "|".join(re.escape(kw) for kw in action_keywords)

    placeholders = {
        "{SYMBOL}": _build_symbol_pattern(usr),
        "{ACTION}": rf"(?P<ACTION>{action_pattern})",
        "{ENTRY}": r"(?P<ENTRY>[0-9]+(?:\.[0-9]+)?)",
        "{SL}": r"(?P<SL>[0-9]+(?:\.[0-9]+)?)",
        "{IGNORE}": r".*",
    }

    regex = re.escape(pattern)
    regex = regex.replace('\\ ', r'\s+')  # spazio escaped → \s+
    regex = regex.replace('\\\n', r'\s+')  # newline escaped → \s+

    tp_count = pattern.count("{TP}")

    for i in range(1, tp_count + 1):
        regex = regex.replace(
            re.escape("{TP}"),
            r"(?P<TP" + str(i) + r">[0-9]+(?:\.[0-9]+)?)",
            1
        )

    for ph, rx in placeholders.items():
        regex = regex.replace(re.escape(ph), rx)

    try:
        match = re.search(regex, text, re.DOTALL | re.IGNORECASE)
    except re.error:
        logger.error(f"[ANALYZER] Pattern regex non valida per chat={chat_id}")
        return None

    if not match:
        return None

    groups = match.groupdict()

    # Risolve la keyword trovata → tipo azione (es. "vendi" → "SELL")
    matched_action = groups.get("ACTION", "")
    action = _resolve_action(matched_action, keywords)
    if action is None:
        return None

    tp = []
    for i in range(1, tp_count + 1):
        val = groups.get(f"TP{i}")
        if val:
            tp.append(float(val))

    return Signal(
        symbol=groups.get("SYMBOL") or "",
        action=action,
        entry=float(groups["ENTRY"]) if groups.get("ENTRY") else None,
        sl=float(groups["SL"]) if groups.get("SL") else None,
        tp=tp,
        raw_text=text,
        source_chat_id=chat_id
    )


# ──────────────────────────────────────────────
# Symbol helpers (TODO 2)
# ──────────────────────────────────────────────
def _find_symbol(line_upper: str, keywords: dict[str, list[str]], usr: User) -> str | None:
    """
    Cerca il simbolo in una riga di testo (già in MAIUSCOLO).
    1. Prima cerca tra i SYMBOLS configurati nel DB (più preciso, supporta US30/NAS100/GOLD)
    2. Fallback: regex generica [A-Z][A-Z0-9]{1,9} escludendo le keyword note
    """
    symbols = getSymbols(usr)
    for sym_tg in sorted(symbols, key=len, reverse=True):
        if re.search(r'\b' + re.escape(sym_tg) + r'\b', line_upper):
            return sym_tg

    all_kw = [k for lst in keywords.values() for k in lst]
    match = re.search(r'\b[A-Z][A-Z0-9]{1,9}\b', line_upper)
    if match:
        candidate = match.group()
        if candidate.lower() not in all_kw:
            return candidate
    return None


def _build_symbol_pattern(usr: User) -> str:
    """
    Costruisce la regex per il placeholder {SYMBOL} nel pattern parser.
    Se ci sono simboli configurati nel DB, li usa (supporta US30/NAS100).
    Fallback: regex generica.
    """
    symbols = getSymbols(usr)
    if not symbols:
        return r"(?P<SYMBOL>[A-Z][A-Z0-9]{1,9})"
    sorted_syms = sorted(symbols, key=len, reverse=True)
    sym_pattern = "|".join(re.escape(s) for s in sorted_syms)
    return rf"(?P<SYMBOL>{sym_pattern})"


# ──────────────────────────────────────────────
# Utility
# ──────────────────────────────────────────────
def _resolve_action(matched_keyword: str, keywords: dict[str, list[str]]) -> str | None:
    """
    Data una keyword trovata nel testo (es. "vendi"),
    ritorna il tipo azione standardizzato (es. "SELL").
    Ritorna None se non trovato.
    """
    matched_lower = matched_keyword.lower()
    for ktype, kw_list in keywords.items():
        if matched_lower in kw_list:
            return ktype
    return None


def _contains_skip(text: str, skip_keywords: list[str]) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in skip_keywords)


def _extract_first_number(text: str) -> float | None:
    match = re.search(r"[0-9]+(?:\.[0-9]+)?", text)
    return float(match.group()) if match else None


def _extract_all_numbers(text: str) -> list[float]:
    return [float(m) for m in re.findall(r"[0-9]+(?:\.[0-9]+)?", text)]
