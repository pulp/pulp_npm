from gettext import gettext as _

from pulpcore.plugin.exceptions import PulpException


class RemoteURLRequiredError(PulpException):
    """
    Raised when a remote does not have a URL specified for sync.
    """

    error_code = "NPM0001"

    def __str__(self):
        return f"[{self.error_code}] " + _("A remote must have a url specified to synchronize.")


class MissingArtifactError(PulpException):
    """
    Raised when an artifact is required but not provided.
    """

    error_code = "NPM0002"

    def __str__(self):
        return f"[{self.error_code}] " + _("An artifact is required to create npm package content.")


class MetadataExtractionError(PulpException):
    """
    Raised when metadata cannot be extracted from an npm tarball.
    """

    error_code = "NPM0003"

    def __init__(self, error_message):
        """
        Set the exception details.

        Args:
            error_message(str): The error message from the extraction attempt
        """
        self.error_message = error_message

    def __str__(self):
        return f"[{self.error_code}] " + _(
            "Could not extract metadata from npm tarball: {error}. "
            "Please provide 'name' and 'version' explicitly."
        ).format(error=self.error_message)
