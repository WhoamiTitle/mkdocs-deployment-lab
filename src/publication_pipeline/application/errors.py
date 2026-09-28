"""Application-level errors exposed by the publication pipeline."""


class PublicationError(RuntimeError):
    """Base class for an expected pipeline failure."""


class InvalidArtifactError(PublicationError):
    """The generated site does not satisfy the deployment contract."""


class HealthcheckError(PublicationError):
    """The deployed site did not pass its healthcheck."""


class RollbackUnavailableError(PublicationError):
    """There is no previous release to activate."""


class UnsafePathError(PublicationError):
    """A path could escape the configured deployment area."""
