"""Custom Errors and Exceptions for TIAToolbox."""


class FileNotSupportedError(Exception):
    """Raise No supported file found error.

    Args:
        message (str) : Display message for the error.

    """

    def __init__(
        self: Exception,
        message: str = "File format is not supported",
    ) -> None:
        """Initialize :class:`FileNotSupportedError`."""
        super().__init__(message)


class MethodNotSupportedError(Exception):
    """Raise No supported file found error.

    Args:
        message (str) : Display message for the error.

    """

    def __init__(self: Exception, message: str = "Method is not supported") -> None:
        """Initialize :class:`MethodNotSupportedError`."""
        super().__init__(message)
