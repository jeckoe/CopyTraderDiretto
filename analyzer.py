# analyzer.py
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime

from User import User
from gestoreDB import getActiveDialogs, getSignalKeywords, getSkipKeywords, saveUnrecognized

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Signal — temporaneo qui, verrà spostato in signal_model.py
# ──────────────────────────────────────────────
@dataclass
class Signal:
    symbol: str
    action: str
    entry: float | None
    sl: float | None
    tp: list[float]
    raw_text: str
    source_chat_id: str
    timestamp: datetime = field(default_factory=datetime.now)


# ──────────────────────────────────────────────
# Cache chat attive — ricaricata all'avvio
# ──────────────────────────────────────────────
_active_dialogs: dict[str, dict] = {}


def load_active_dialogs(usr: User) -> None:
    """
    Carica dal DB le chat con IS_ACTIVE = 1 e le mette in un dizionario
    indicizzato per DIALOG_ID (stringa).
    Viene chiamata una volta sola all'avvio da main.py.
    """
    global _active_dialogs
    dialogs = getActiveDialogs(usr)
    _active_dialogs = {str(d["dialog_id"]): d for d in dialogs}
    logger.info(f"[ANALYZER] {len(_active_dialogs)} chat attive caricate.")


# ──────────────────────────────────────────────
# Funzione pubblica — entry point dell'analyzer
# ──────────────────────────────────────────────
def analyze(usr: User, chat_id: str, sender_id: str | None, text: str) -> Signal | None:
    """
    Riceve un messaggio grezzo e tenta di estrarre un segnale.
    Ritorna un Signal se il parsing ha successo, None altrimenti.
    Se il messaggio non è riconoscibile, lo salva nel DB per review manuale.
    """

    # 1. La chat è attiva?
    if chat_id not in _active_dialogs:
        return None

    dialog = _active_dialogs[chat_id]
    dialog_pk = dialog["pk"]
    text_clean = text.strip()

    # 2. Contiene skip keywords?
    skip = getSkipKeywords(usr, dialog_pk)
    if _contains_skip(text_clean, skip):
        logger.info(f"[ANALYZER] Messaggio skippato (skip keyword trovata). chat={chat_id}")
        return None

    # 3. Prova il parser appropriato
    pattern = dialog.get("pattern")  # None se non definito
    signal = None

    if pattern:
        signal = _parse_with_pattern(text_clean, pattern, chat_id)
        if signal is None:
            # Pattern fallisce → prova il keyword parser come fallback
            logger.warning(f"[ANALYZER] Pattern non matchato, provo keyword parser. chat={chat_id}")
            signal = _parse_with_keywords(text_clean, usr, dialog_pk, chat_id)
    else:
        signal = _parse_with_keywords(text_clean, usr, dialog_pk, chat_id)

    # 4. Nessun segnale trovato → salva come non riconosciuto
    if signal is None:
        logger.info(f"[ANALYZER] Messaggio non riconosciuto, salvato nel DB. chat={chat_id}")
        saveUnrecognized(usr, chat_id, sender_id, text_clean)

    return signal


# ──────────────────────────────────────────────
# Parser 1 — Keyword (generico, default)
# ──────────────────────────────────────────────
def _parse_with_keywords(text: str, usr: User, dialog_pk: int | None, chat_id: str) -> Signal | None:
    """
    Scansiona il testo riga per riga cercando keyword + numeri.
    Non dipende dalla posizione dei campi nel messaggio.
    """
    keywords = getSignalKeywords(usr, dialog_pk)
    lines = [l.strip().lower() for l in text.splitlines() if l.strip()]

    symbol = None
    action = None
    entry = None
    sl = None
    tp = []

    for line in lines:
        # Cerca azione
        if action is None:
            for ktype in ("BUY", "SELL", "BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP"):
                if any(kw in line for kw in keywords.get(ktype, [])):
                    action = ktype
                    break

        # Cerca symbol — parola in maiuscolo di 3-10 caratteri senza numeri
        if symbol is None:
            match = re.search(r'\b[A-Z]{2,10}\b', line.upper())
            if match:
                candidate = match.group()
                # Evita di prendere le keyword stesse come symbol
                all_kw = [k for lst in keywords.values() for k in lst]
                if candidate.lower() not in all_kw:
                    symbol = candidate

        # Cerca entry
        if entry is None and any(kw in line for kw in keywords.get("ENTRY", [])):
            entry = _extract_first_number(line)

        # Cerca SL
        if sl is None and any(kw in line for kw in keywords.get("SL", [])):
            sl = _extract_first_number(line)

        # Cerca TP (fino a 3)
        if len(tp) < 3 and any(kw in line for kw in keywords.get("TP", [])):
            # Gestisce TP multipli sulla stessa riga separati da /
            numbers = _extract_all_numbers(line)
            for n in numbers:
                if len(tp) < 3:
                    tp.append(n)

    # Valida — symbol e action sono obbligatori
    if symbol is None or action is None:
        return None

    return Signal(
        symbol=symbol,
        action=action,
        entry=entry,
        sl=sl,
        tp=tp,
        raw_text=text,
        source_chat_id=chat_id
    )


# ──────────────────────────────────────────────
# Parser 2 — Pattern template (specifico per canale)
# ──────────────────────────────────────────────
def _parse_with_pattern(text: str, pattern: str, chat_id: str) -> Signal | None:
    """
    Usa un template con placeholder fissi per estrarre i campi.
    Esempio di pattern: "{SYMBOL} {ACTION} @ {ENTRY}\\nSL: {SL}\\nTP: {TP}"
    """
    # Converte il pattern in una regex, un placeholder alla volta
    placeholders = {
        "{SYMBOL}": r"(?P<SYMBOL>[A-Z]{2,10})",
        "{ACTION}": r"(?P<ACTION>BUY LIMIT|SELL LIMIT|BUY STOP|SELL STOP|BUY|SELL)",
        "{ENTRY}": r"(?P<ENTRY>[0-9]+(?:\.[0-9]+)?)",
        "{SL}": r"(?P<SL>[0-9]+(?:\.[0-9]+)?)",
        "{TP}": r"(?P<TP>[0-9]+(?:\.[0-9]+)?)",
        "{IGNORE}": r".*?",
    }

    regex = re.escape(pattern)
    tp_count = pattern.count("{TP}")

    # Rinomina i TP multipli → TP1, TP2, TP3 nella regex
    for i in range(1, tp_count + 1):
        regex = regex.replace(
            re.escape("{TP}"),
            r"(?P<TP" + str(i) + r">[0-9]+(?:\.[0-9]+)?)",
            1
        )

    # Sostituisce gli altri placeholder
    for ph, rx in placeholders.items():
        if ph != "{TP}":
            regex = regex.replace(re.escape(ph), rx)

    try:
        match = re.search(regex, text, re.DOTALL | re.IGNORECASE)
    except re.error:
        logger.error(f"[ANALYZER] Pattern regex non valida per chat={chat_id}")
        return None

    if not match:
        return None

    groups = match.groupdict()
    tp = []
    for i in range(1, tp_count + 1):
        val = groups.get(f"TP{i}")
        if val:
            tp.append(float(val))

    return Signal(
        symbol=groups.get("SYMBOL") or "",
        action=groups.get("ACTION") or "",
        entry=float(groups["ENTRY"]) if groups.get("ENTRY") else None,
        sl=float(groups["SL"]) if groups.get("SL") else None,
        tp=tp,
        raw_text=text,
        source_chat_id=chat_id
    )


# ──────────────────────────────────────────────
# Utility
# ──────────────────────────────────────────────
def _contains_skip(text: str, skip_keywords: list[str]) -> bool:
    """Ritorna True se il testo contiene almeno una skip keyword."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in skip_keywords)


def _extract_first_number(text: str) -> float | None:
    """Estrae il primo numero decimale trovato nel testo."""
    match = re.search(r"[0-9]+(?:\.[0-9]+)?", text)
    return float(match.group()) if match else None


def _extract_all_numbers(text: str) -> list[float]:
    """Estrae tutti i numeri decimali trovati nel testo."""
    return [float(m) for m in re.findall(r"[0-9]+(?:\.[0-9]+)?", text)]
