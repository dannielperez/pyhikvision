"""pyhikvision — unified Hikvision toolkit (ISAPI + NetSDK).

Public API:
    HikClient        — high-level facade (defaults to ISAPI)
    IsapiClient      — pure-Python ISAPI client (low-level)
    batch_set_ip     — parallel IP-change helper for migrations
    DeviceInfo, NetworkConfig — dataclasses
    HikError, HikAuthError, HikHTTPError, HikXMLError, HikUnreachableError
"""

from .client import HikClient
from .isapi import IsapiClient, batch_set_ip
from .models import DeviceInfo, NetworkConfig
from .exceptions import (
    HikError,
    HikAuthError,
    HikHTTPError,
    HikXMLError,
    HikUnreachableError,
)

__version__ = "0.1.0"

__all__ = [
    "HikClient",
    "IsapiClient",
    "batch_set_ip",
    "DeviceInfo",
    "NetworkConfig",
    "HikError",
    "HikAuthError",
    "HikHTTPError",
    "HikXMLError",
    "HikUnreachableError",
    "__version__",
]
