"""High-level :class:`HikClient` facade — defaults to ISAPI.

Choose backend explicitly with ``backend="isapi" | "netsdk"``. NetSDK is
Linux-only and currently only covers SDK-bound operations not in ISAPI.
"""

from __future__ import annotations

from typing import Optional

from .isapi.client import IsapiClient
from .models import DeviceInfo, NetworkConfig


class HikClient:
    """Backend-aware Hikvision client.

    Currently delegates everything to ISAPI. NetSDK methods raise
    :class:`NotImplementedError` until the bindings are wired up — this
    matches the merged-roadmap intent without forcing native deps on
    every consumer.
    """

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        *,
        backend: str = "isapi",
        port: Optional[int] = None,
        scheme: str = "http",
        timeout: float = 10.0,
        verify_tls: bool = False,
        interface_id: int = 1,
    ) -> None:
        self.backend = backend.lower()
        if self.backend == "isapi":
            self._impl = IsapiClient(
                host,
                user,
                password,
                port=port,
                scheme=scheme,
                timeout=timeout,
                verify_tls=verify_tls,
                interface_id=interface_id,
            )
        elif self.backend == "netsdk":
            from .netsdk import NetSdkClient

            self._impl = NetSdkClient(host, user, password, port=port or 8000)
        else:
            raise ValueError(f"unknown backend: {backend!r}")

        self.host = host
        self.user = user
        self.password = password

    def __enter__(self):
        if hasattr(self._impl, "__enter__"):
            self._impl.__enter__()
        return self

    def __exit__(self, exc_type, exc, tb):
        if hasattr(self._impl, "__exit__"):
            return self._impl.__exit__(exc_type, exc, tb)
        return False

    def close(self) -> None:
        if hasattr(self._impl, "close"):
            self._impl.close()

    # ---- delegated API (ISAPI surface) ----
    def device_info(self) -> DeviceInfo:
        return self._impl.device_info()

    def get_network_config(self) -> NetworkConfig:
        return self._impl.get_network_config()

    def set_network_config(self, **kwargs) -> None:
        return self._impl.set_network_config(**kwargs)

    def reboot(self) -> None:
        return self._impl.reboot()
