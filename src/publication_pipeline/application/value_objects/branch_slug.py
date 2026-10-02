import hashlib
import re
from dataclasses import dataclass
from typing import ClassVar, Self

from publication_pipeline.application.value_objects.branch_name import BranchName


@dataclass(frozen=True, slots=True, repr=False)
class BranchSlug:
    MAX_LEN: ClassVar[int] = 57
    SAFE_SEGMENT: ClassVar[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9._-]+$")
    UNSAFE_CHARS: ClassVar[re.Pattern[str]] = re.compile(r"[^a-z0-9._-]+")
    MULTIPLE_DASHES: ClassVar[re.Pattern[str]] = re.compile(r"-{2,}")

    value: str

    def __post_init__(self) -> None:
        if (
            len(self.value) > self.MAX_LEN
            or self.value in {".", ".."}
            or self.SAFE_SEGMENT.fullmatch(self.value) is None
        ):
            raise ValueError(f"Unsafe branch slug: {self.value!r}")

    @classmethod
    def from_branch(cls, branch: BranchName) -> Self:
        normalized = cls.UNSAFE_CHARS.sub("-", branch.value.strip().lower())
        normalized = cls.MULTIPLE_DASHES.sub("-", normalized).strip(".-")
        base = (normalized or "branch")[:48].rstrip(".-")
        digest = hashlib.sha256(branch.value.encode("utf-8")).hexdigest()[:8]
        return cls(f"{base}-{digest}")
