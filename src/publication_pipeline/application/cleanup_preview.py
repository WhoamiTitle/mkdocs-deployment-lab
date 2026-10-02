"""Use case for removing one branch preview after explicit confirmation."""

from dataclasses import dataclass

from publication_pipeline.application.errors import PublicationError
from publication_pipeline.application.models import PreviewCleanupReceipt
from publication_pipeline.application.ports import PreviewCleaner
from publication_pipeline.application.value_objects.branch_name import BranchName
from publication_pipeline.application.value_objects.branch_slug import BranchSlug


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
        branch_name = BranchName(request.branch)
        return self._cleaner.cleanup_preview(BranchSlug.from_branch(branch_name))
