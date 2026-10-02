"""Application-level errors exposed by the publication pipeline."""


class PublicationError(RuntimeError):
    """Base class for an expected pipeline failure."""


class InfrastructureError(PublicationError):
    """Base class for a failure translated at an infrastructure boundary."""


class SourceControlError(InfrastructureError):
    """Source-control metadata could not be read reliably."""


class SiteBuildError(InfrastructureError):
    """The configured static-site builder failed."""


class HttpClientError(InfrastructureError):
    """The HTTP transport could not complete a request."""


class LocalDeploymentError(InfrastructureError):
    """A local filesystem deployment operation failed."""


class RemoteExecutionError(InfrastructureError):
    """An SSH or rsync operation failed or exceeded its deadline."""


class InvalidArtifactError(PublicationError):
    """The generated site does not satisfy the deployment contract."""


class HealthcheckError(PublicationError):
    """The deployed site did not pass its healthcheck."""


class RollbackUnavailableError(PublicationError):
    """There is no previous release to activate."""


class UnsafePathError(PublicationError):
    """A path could escape the configured deployment area."""
