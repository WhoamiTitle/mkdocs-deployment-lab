"""Use case for removing one branch preview after explicit confirmation."""

from dataclasses import dataclass

from publication_pipeline.application.errors import PublicationError
from publication_pipeline.application.models import BranchSlug, PreviewCleanupReceipt
from publication_pipeline.application.ports import PreviewCleaner


@dataclass(frozen=True, slots=True, kw_only=True)
class CleanupPreviewRequest:
    branch: str
    confirmed_branch: str


class CleanupPreview:
    def __init__(self, cleaner: PreviewCleaner) -> None:
        self._cleaner = cleaner

    def execute(self, request: CleanupPreviewRequest) -> PreviewCleanupReceipt:
        if request.branch != request.confirmed_branch:
            raise PublicationError("Preview cleanup requires an exact branch confirmation")
        return self._cleaner.cleanup_preview(BranchSlug.from_branch(request.branch))
