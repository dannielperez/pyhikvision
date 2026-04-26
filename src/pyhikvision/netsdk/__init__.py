"""NetSDK backend — ctypes bindings to Hikvision HCNetSDK (Linux only).

Status: **skeleton**. The IP-migration workflow uses ISAPI; this backend
is reserved for features ISAPI cannot cover (SADP discovery, RTSP playback,
video search). Drop the official Linux HCNetSDK bundle into
``binaries/linux/<arch>/`` (or set ``HIKVISION_SDK_DIR``) before importing.

This module intentionally does *nothing* at import time. Calling any
function requires the SDK to be loadable; otherwise a clear
:class:`NotImplementedError` is raised.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

_SDK_DIR_ENV = "HIKVISION_SDK_DIR"


def sdk_directory() -> Optional[Path]:
    """Resolve the directory containing libhcnetsdk.so."""
    env = os.environ.get(_SDK_DIR_ENV)
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    here = Path(__file__).resolve().parent.parent.parent.parent  # package root
    arch = "arm64" if "arm" in (os.uname().machine if hasattr(os, "uname") else "") else "x86_64"
    candidate = here / "binaries" / "linux" / arch
    return candidate if candidate.is_dir() else None


def is_available() -> bool:
    """Return True iff the HCNetSDK shared object is loadable on this host."""
    if sys.platform != "linux":
        return False
    d = sdk_directory()
    if d is None:
        return False
    return any((d / name).exists() for name in ("libhcnetsdk.so", "libHCNetSDK.so"))


class NetSdkClient:
    """Placeholder for the HCNetSDK-backed client.

    Methods will raise :class:`NotImplementedError` until the corresponding
    binding is wired up. ISAPI covers IP migration; this backend is opt-in
    for the SDK-bound features.
    """

    def __init__(self, host: str, user: str, password: str, port: int = 8000) -> None:
        if not is_available():
            raise NotImplementedError(
                "HCNetSDK is not available. Drop the Linux bundle into "
                "packages/pyhikvision/binaries/linux/<arch>/ or set "
                f"{_SDK_DIR_ENV}, and run on Linux."
            )
        self.host = host
        self.user = user
        self.password = password
        self.port = port

    def list_streams(self):
        raise NotImplementedError("netsdk.list_streams not yet wired")

    def search_recordings(self, *args, **kwargs):
        raise NotImplementedError("netsdk.search_recordings not yet wired")

    def sadp_scan(self):
        raise NotImplementedError("netsdk.sadp_scan not yet wired")
