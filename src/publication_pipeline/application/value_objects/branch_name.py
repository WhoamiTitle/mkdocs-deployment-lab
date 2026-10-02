from dataclasses import dataclass


@dataclass(frozen=True, slots=True, repr=False)
class BranchName:
    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("Branch name must be non-blank")
