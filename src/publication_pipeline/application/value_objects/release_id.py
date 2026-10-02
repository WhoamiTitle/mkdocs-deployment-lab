import re
from dataclasses import dataclass
from typing import ClassVar, Self

from publication_pipeline.application.value_objects.commit_sha import CommitSha
from publication_pipeline.application.value_objects.utc_datetime import UtcDatetime


@dataclass(frozen=True, slots=True, repr=False)
class ReleaseId:
    MAX_LEN: ClassVar[int] = 128
    PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]+$")

    value: str

    def __post_init__(self) -> None:
        if (
            len(self.value) > self.MAX_LEN
            or self.value in {".", ".."}
            or self.PATTERN.fullmatch(self.value) is None
        ):
            raise ValueError(f"Unsafe release ID: {self.value!r}")

    @classmethod
    def create(cls, commit_sha: CommitSha, built_at: UtcDatetime) -> Self:
        return cls(f"{commit_sha.value[:12]}-{built_at.value:%Y%m%dT%H%M%SZ}")
