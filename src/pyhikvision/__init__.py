"""pyhikvision — unified Hikvision toolkit (ISAPI + NetSDK).

Public API:
    HikClient        — high-level facade (defaults to ISAPI)
    IsapiClient      — pure-Python ISAPI client (low-level)
    batch_set_ip     — parallel IP-change helper for migrations
    DeviceInfo, NetworkConfig, LineDetectionConfig — dataclasses
    HikError, HikAuthError, HikHTTPError, HikUnsupportedPasswordEncodingError,
    HikXMLError, HikUnreachableError
"""

from .client import HikClient
from .exceptions import (
    HikAuthError,
    HikError,
    HikHTTPError,
    HikUnsupportedPasswordEncodingError,
    HikUnreachableError,
    HikXMLError,
)
from .isapi import IsapiClient, batch_set_ip
from .models import ChannelInfo, DeviceInfo, LineDetectionConfig, NetworkConfig

__version__ = "0.1.0"

__all__ = [
    "HikClient",
    "IsapiClient",
    "batch_set_ip",
    "ChannelInfo",
    "DeviceInfo",
    "NetworkConfig",
    "LineDetectionConfig",
    "HikError",
    "HikAuthError",
    "HikHTTPError",
    "HikUnsupportedPasswordEncodingError",
    "HikXMLError",
    "HikUnreachableError",
    "__version__",
]
