"""Use case for removing one branch preview after explicit confirmation."""

from publication_pipeline.application.errors import PublicationError
from publication_pipeline.application.models import PreviewCleanupReceipt, branch_to_slug
from publication_pipeline.application.ports import PreviewCleaner


class CleanupPreview:
    def __init__(self, cleaner: PreviewCleaner) -> None:
        self._cleaner = cleaner

    def execute(self, branch: str, confirmed_branch: str) -> PreviewCleanupReceipt:
        if branch != confirmed_branch:
            raise PublicationError("Preview cleanup requires an exact branch confirmation")
        return self._cleaner.cleanup_preview(branch_to_slug(branch))
