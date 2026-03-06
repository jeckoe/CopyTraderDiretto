from dataclasses import dataclass, field
from datetime import datetime


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
