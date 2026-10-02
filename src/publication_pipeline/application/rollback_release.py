"""Production rollback use case."""

from publication_pipeline.application.models import DeploymentReceipt
from publication_pipeline.application.ports import ReleaseRollback


class RollbackRelease:
    def __init__(self, publisher: ReleaseRollback) -> None:
        self._publisher = publisher

    def execute(self) -> DeploymentReceipt:
        return self._publisher.rollback()
