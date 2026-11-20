"""failure.py -- exception types shared by harness.py and image.py."""


class CheckFailure(AssertionError):
    """Raise from a check to fail it with a readable explanation."""

    def __init__(self, expected=None, actual=None, hint="", message=""):
        super().__init__(message or f"expected {expected}, got {actual}")
        self.expected, self.actual, self.hint, self.message = expected, actual, hint, message


class HarnessError(Exception):
    """Tooling/infrastructure problem (exit code 2), not the reader's fault."""
