import mimetypes

from pulpcore.plugin.content import Handler


class NpmContentHandler(Handler):
    """
    Serve npm repositories.

    """

    @staticmethod
    def response_headers(path):
        """
        Get the Content-Type and Encoding-Type headers for the requested `path`.

        Args:
            path (str): The relative path that was requested.

        Returns:
            headers (dict): A dictionary of response headers.

        """
        content_type, encoding = mimetypes.guess_type(path)
        headers = {}

        if content_type:
            headers["Content-Type"] = content_type

        return headers
