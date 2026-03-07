"""
mt5_executor.py — Esecuzione ordini su MetaTrader 5

Flusso:
  1. Riceve un Signal e il dialog da cui proviene
  2. Determina su quali account MT5 operare (mappatura DIALOG→MT5_ACCOUNT)
  3. Per ogni account: connette, mappa il symbol, invia l'ordine
  4. Disconnette l'account

Decisioni architetturali:
  - MT5_ACCOUNT_ID su DIALOGS è opzionale:
      NULL → usa tutti gli account MT5 dell'utente
      specificato → usa solo quell'account
  - LOT_SIZE configurato per account in MT5_ACCOUNTS (default 0.01)
  - BUY/SELL → ordine a mercato
  - BUY_LIMIT/SELL_LIMIT/BUY_STOP/SELL_STOP → ordine pending
  - Primo TP usato come TP dell'ordine; eventuali TP aggiuntivi sono solo informativi
  - MetaTrader5 package è opzionale: se non installato il resto dell'app funziona uguale
"""

import logging
from typing import TYPE_CHECKING

from User import User
from signal_model import Signal
from gestoreDB import getMT5Accounts, getSymbols

logger = logging.getLogger(__name__)

# Importazione opzionale — MetaTrader5 funziona solo su Windows con MT5 installato
try:
    import MetaTrader5 as mt5
    _MT5_AVAILABLE = True
except ImportError:
    mt5 = None
    _MT5_AVAILABLE = False
    logger.warning("[MT5] Package MetaTrader5 non installato. Executor disabilitato.")


# Mappa action string → tipo ordine MT5
_ORDER_TYPE_MAP = {
    "BUY":        "BUY",
    "SELL":       "SELL",
    "BUY_LIMIT":  "BUY_LIMIT",
    "SELL_LIMIT": "SELL_LIMIT",
    "BUY_STOP":   "BUY_STOP",
    "SELL_STOP":  "SELL_STOP",
}

_MARKET_ORDERS = {"BUY", "SELL"}
_PENDING_ORDERS = {"BUY_LIMIT", "SELL_LIMIT", "BUY_STOP", "SELL_STOP"}


def execute_signal(usr: User, signal: Signal, mt5_account_id: int | None) -> None:
    """
    Entry point principale. Invia il segnale su uno o tutti gli account MT5.

    Args:
        usr: utente corrente
        signal: segnale da eseguire
        mt5_account_id: ID account specifico (da DIALOGS.MT5_ACCOUNT_ID),
                        None = usa tutti gli account dell'utente
    """
    if not _MT5_AVAILABLE:
        logger.error("[MT5] Impossibile eseguire: MetaTrader5 non disponibile.")
        return

    action_upper = signal.action.upper()
    if action_upper not in _ORDER_TYPE_MAP:
        logger.warning(f"[MT5] Action '{signal.action}' non mappata a nessun tipo ordine MT5. Saltato.")
        return

    accounts = getMT5Accounts(usr, account_id=mt5_account_id)
    if not accounts:
        logger.warning(f"[MT5] Nessun account MT5 trovato per utente={usr.ID} account_id={mt5_account_id}")
        return

    for account in accounts:
        _execute_on_account(usr, signal, account, action_upper)


def _execute_on_account(usr: User, signal: Signal, account: dict, action: str) -> None:
    """Esegue il segnale su un singolo account MT5."""
    label = account.get("label") or account["login"]

    # Connessione
    ok = mt5.initialize(
        login=int(account["login"]),
        password=account["password"],
        server=account["server"],
    )
    if not ok:
        error = mt5.last_error()
        logger.error(f"[MT5] Connessione fallita su account '{label}': {error}")
        return

    logger.info(f"[MT5] Connesso a account '{label}'")

    try:
        # Mapping symbol TG → MT5
        symbols_map = getSymbols(usr, mt5_account_id=account["id"])
        symbol_mt5 = symbols_map.get(signal.symbol.upper(), signal.symbol)

        # Verifica che il symbol esista su MT5
        symbol_info = mt5.symbol_info(symbol_mt5)
        if symbol_info is None:
            logger.error(f"[MT5] Symbol '{symbol_mt5}' non trovato su account '{label}'")
            return

        if not symbol_info.visible:
            mt5.symbol_select(symbol_mt5, True)

        lot_size = account.get("lot_size") or 0.01
        tp_price = signal.tp[0] if signal.tp else None

        if action in _MARKET_ORDERS:
            _send_market_order(label, symbol_mt5, action, lot_size, signal.sl, tp_price)
        elif action in _PENDING_ORDERS:
            if signal.entry is None:
                logger.warning(f"[MT5] Ordine pending '{action}' senza entry price. Saltato su '{label}'.")
                return
            _send_pending_order(label, symbol_mt5, action, lot_size, signal.entry, signal.sl, tp_price)

    finally:
        mt5.shutdown()
        logger.info(f"[MT5] Disconnesso da account '{label}'")


def _send_market_order(label: str, symbol: str, action: str,
                       lot: float, sl: float | None, tp: float | None) -> None:
    """Invia un ordine a mercato (BUY o SELL)."""
    order_type = mt5.ORDER_TYPE_BUY if action == "BUY" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        logger.error(f"[MT5] Impossibile ottenere prezzo corrente per '{symbol}' su '{label}'")
        return

    price = tick.ask if action == "BUY" else tick.bid

    request = {
        "action":   mt5.TRADE_ACTION_DEAL,
        "symbol":   symbol,
        "volume":   lot,
        "type":     order_type,
        "price":    price,
        "sl":       sl or 0.0,
        "tp":       tp or 0.0,
        "deviation": 20,
        "magic":    20250307,
        "comment":  "CopyTraderDiretto",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    _log_order_result(label, symbol, action, result)


def _send_pending_order(label: str, symbol: str, action: str, lot: float,
                        entry: float, sl: float | None, tp: float | None) -> None:
    """Invia un ordine pending (LIMIT o STOP)."""
    type_map = {
        "BUY_LIMIT":  mt5.ORDER_TYPE_BUY_LIMIT,
        "SELL_LIMIT": mt5.ORDER_TYPE_SELL_LIMIT,
        "BUY_STOP":   mt5.ORDER_TYPE_BUY_STOP,
        "SELL_STOP":  mt5.ORDER_TYPE_SELL_STOP,
    }

    request = {
        "action":   mt5.TRADE_ACTION_PENDING,
        "symbol":   symbol,
        "volume":   lot,
        "type":     type_map[action],
        "price":    entry,
        "sl":       sl or 0.0,
        "tp":       tp or 0.0,
        "magic":    20250307,
        "comment":  "CopyTraderDiretto",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_RETURN,
    }

    result = mt5.order_send(request)
    _log_order_result(label, symbol, action, result)


def _log_order_result(label: str, symbol: str, action: str, result) -> None:
    if result is None:
        logger.error(f"[MT5] order_send ha ritornato None. account='{label}' {symbol} {action}")
        return

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        logger.info(
            f"[MT5] Ordine eseguito. account='{label}' symbol={symbol} action={action} "
            f"ticket={result.order} price={result.price} volume={result.volume}"
        )
    else:
        logger.error(
            f"[MT5] Ordine fallito. account='{label}' symbol={symbol} action={action} "
            f"retcode={result.retcode} comment={result.comment}"
        )
