from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True, repr=False)
class UtcDatetime:
    value: datetime

    def __post_init__(self) -> None:
        self._ensure_is_timezone_aware(self.value)
        object.__setattr__(self, "value", self._normalize(self.value))

    @classmethod
    def _ensure_is_timezone_aware(cls, value: datetime) -> None:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{cls.__name__}: timezone-aware datetime required")

    @classmethod
    def _normalize(cls, value: datetime) -> datetime:
        return value.astimezone(UTC)
