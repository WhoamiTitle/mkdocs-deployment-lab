import re
from dataclasses import dataclass
from typing import ClassVar


@dataclass(frozen=True, slots=True, repr=False)
class CommitSha:
    PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")

    value: str

    def __post_init__(self) -> None:
        if self.PATTERN.fullmatch(self.value) is None:
            raise ValueError(f"Invalid commit SHA: {self.value!r}")
