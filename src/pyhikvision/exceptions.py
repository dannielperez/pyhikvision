"""Exceptions raised by pyhikvision."""


class HikError(Exception):
    """Base exception for all pyhikvision errors."""


class HikAuthError(HikError):
    """Authentication failed (401 / wrong credentials)."""


class HikHTTPError(HikError):
    """Non-2xx HTTP response from ISAPI endpoint."""

    def __init__(self, status: int, url: str, body: str = ""):
        self.status = status
        self.url = url
        self.body = body
        super().__init__(f"HTTP {status} from {url}: {body[:200]}")


class HikXMLError(HikError):
    """ISAPI returned malformed/unexpected XML."""


class HikUnreachableError(HikError):
    """TCP connection to camera/NVR failed."""
