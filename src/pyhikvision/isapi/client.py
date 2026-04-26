"""High-level Hikvision ISAPI client.

Pure-Python HTTP(S) + Digest auth. Works wherever ``requests`` works,
including over WireGuard / routed links. No native SDK required.

Endpoints implemented (sufficient for IP-migration workflows):

- GET  /ISAPI/System/deviceInfo
- GET  /ISAPI/System/Network/interfaces/{n}/ipAddress
- PUT  /ISAPI/System/Network/interfaces/{n}/ipAddress
- PUT  /ISAPI/System/reboot

Reference: Hikvision ISAPI 2.x specification (publicly distributed under
"Hikvision ISAPI Open Platform Network Communication Specification").
"""

from __future__ import annotations

import logging
import time
from typing import Optional

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,
    Timeout as RequestsTimeout,
)

from .._xml import find_local_text, parse, set_local_text, to_xml
from ..exceptions import (
    HikAuthError,
    HikError,
    HikHTTPError,
    HikUnreachableError,
    HikXMLError,
)
from ..models import DeviceInfo, NetworkConfig

logger = logging.getLogger(__name__)


class IsapiClient:
    """Hikvision ISAPI client.

    >>> with IsapiClient("192.168.1.64", "admin", "pass") as cam:
    ...     info = cam.device_info()
    ...     cam.set_network_config(ip="10.0.0.10", mask="255.255.255.0",
    ...                            gateway="10.0.0.1")
    ...     cam.reboot()
    """

    def __init__(
        self,
        host: str,
        user: str,
        password: str,
        *,
        port: Optional[int] = None,
        scheme: str = "http",
        timeout: float = 10.0,
        verify_tls: bool = False,
        interface_id: int = 1,
    ) -> None:
        self.host = host
        self.user = user
        self.password = password
        self.scheme = scheme.lower()
        if port is None:
            port = 443 if self.scheme == "https" else 80
        self.port = port
        self.timeout = timeout
        self.verify_tls = verify_tls
        self.interface_id = interface_id

        self._session = requests.Session()
        # Hikvision firmwares vary: some use Digest, older ones Basic.
        # Try Digest first; fall back to Basic on a 401 with WWW-Authenticate
        # advertising Basic.
        self._auth = HTTPDigestAuth(user, password)
        self._fallback_auth = HTTPBasicAuth(user, password)

    # ---- context manager ----
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def close(self) -> None:
        try:
            self._session.close()
        except Exception:
            pass

    # ---- low-level request ----
    @property
    def base_url(self) -> str:
        return f"{self.scheme}://{self.host}:{self.port}"

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self.base_url + path

    def _request(
        self,
        method: str,
        path: str,
        *,
        data: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> requests.Response:
        url = self._url(path)
        headers = {}
        if data is not None:
            headers["Content-Type"] = "application/xml"
        try:
            resp = self._session.request(
                method,
                url,
                auth=self._auth,
                data=data,
                headers=headers,
                timeout=timeout or self.timeout,
                verify=self.verify_tls,
            )
        except (RequestsConnectionError, RequestsTimeout) as exc:
            raise HikUnreachableError(f"{method} {url}: {exc}") from exc

        if resp.status_code == 401:
            # Try Basic auth fallback once
            try:
                resp = self._session.request(
                    method,
                    url,
                    auth=self._fallback_auth,
                    data=data,
                    headers=headers,
                    timeout=timeout or self.timeout,
                    verify=self.verify_tls,
                )
            except (RequestsConnectionError, RequestsTimeout) as exc:
                raise HikUnreachableError(f"{method} {url}: {exc}") from exc
            if resp.status_code == 401:
                raise HikAuthError(f"401 from {url} (digest+basic both failed)")

        if not (200 <= resp.status_code < 300):
            raise HikHTTPError(resp.status_code, url, resp.text)
        return resp

    # ---- device info ----
    def device_info(self) -> DeviceInfo:
        resp = self._request("GET", "/ISAPI/System/deviceInfo")
        try:
            root = parse(resp.text)
        except Exception as exc:
            raise HikXMLError(f"deviceInfo not XML: {exc}") from exc
        return DeviceInfo(
            device_name=find_local_text(root, "deviceName"),
            device_id=find_local_text(root, "deviceID"),
            model=find_local_text(root, "model"),
            serial_number=find_local_text(root, "serialNumber"),
            mac_address=find_local_text(root, "macAddress"),
            firmware_version=find_local_text(root, "firmwareVersion"),
            firmware_released_date=find_local_text(root, "firmwareReleasedDate"),
            device_type=find_local_text(root, "deviceType"),
            raw_xml=resp.text,
        )

    # ---- network config ----
    def get_network_config(self) -> NetworkConfig:
        path = f"/ISAPI/System/Network/interfaces/{self.interface_id}/ipAddress"
        resp = self._request("GET", path)
        try:
            root = parse(resp.text)
        except Exception as exc:
            raise HikXMLError(f"ipAddress not XML: {exc}") from exc
        dhcp_text = find_local_text(root, "addressingType") or ""
        return NetworkConfig(
            ip=find_local_text(root, "ipAddress"),
            mask=find_local_text(root, "subnetMask"),
            gateway=find_local_text(root, "DefaultGateway")
            or find_local_text(root, "ipAddress.1")
            or _find_gateway(root),
            dns1=_find_dns(root, 1),
            dns2=_find_dns(root, 2),
            dhcp=(dhcp_text.lower() == "dynamic") if dhcp_text else None,
            mac_address=find_local_text(root, "macAddress"),
            raw_xml=resp.text,
        )

    def set_network_config(
        self,
        *,
        ip: str,
        mask: str,
        gateway: str,
        dns1: Optional[str] = None,
        dns2: Optional[str] = None,
        dhcp: Optional[bool] = None,
    ) -> None:
        """PUT a new ipAddress block. Roundtrips current XML to preserve
        firmware-specific elements we don't recognise."""
        path = f"/ISAPI/System/Network/interfaces/{self.interface_id}/ipAddress"
        cur = self._request("GET", path)
        try:
            root = parse(cur.text)
        except Exception as exc:
            raise HikXMLError(f"ipAddress (pre-PUT) not XML: {exc}") from exc

        # Set core fields
        if not set_local_text(root, "ipAddress", ip):
            raise HikXMLError("ipAddress element missing in response")
        if not set_local_text(root, "subnetMask", mask):
            raise HikXMLError("subnetMask element missing in response")
        # Gateway lives under <DefaultGateway><ipAddress>...</ipAddress></DefaultGateway>
        _set_gateway(root, gateway)
        if dns1 is not None:
            _set_dns(root, 1, dns1)
        if dns2 is not None:
            _set_dns(root, 2, dns2)
        if dhcp is not None:
            set_local_text(
                root, "addressingType", "dynamic" if dhcp else "static"
            )

        body = to_xml(root)
        self._request("PUT", path, data=body)

    # ---- power ----
    def reboot(self) -> None:
        try:
            self._request("PUT", "/ISAPI/System/reboot", timeout=15.0)
        except HikUnreachableError:
            # Reboot frequently drops the connection mid-response; tolerate.
            return


# --- helpers for nested gateway/DNS XML structures ----------------------


def _find_gateway(root) -> Optional[str]:
    # <DefaultGateway><ipAddress>1.2.3.4</ipAddress></DefaultGateway>
    from .._xml import find_local

    gw = find_local(root, "DefaultGateway")
    if gw is None:
        return None
    return find_local_text(gw, "ipAddress")


def _set_gateway(root, value: str) -> None:
    from .._xml import find_local
    import xml.etree.ElementTree as ET

    gw = find_local(root, "DefaultGateway")
    if gw is None:
        # Some firmwares omit it when DHCP — append a fresh element.
        gw = ET.SubElement(root, "DefaultGateway")
        ip_el = ET.SubElement(gw, "ipAddress")
        ip_el.text = value
        return
    if not set_local_text(gw, "ipAddress", value):
        ip_el = ET.SubElement(gw, "ipAddress")
        ip_el.text = value


def _find_dns(root, idx: int) -> Optional[str]:
    from .._xml import find_local

    # <PrimaryDNS><ipAddress>...</ipAddress></PrimaryDNS>
    # <SecondaryDNS><ipAddress>...</ipAddress></SecondaryDNS>
    name = "PrimaryDNS" if idx == 1 else "SecondaryDNS"
    elem = find_local(root, name)
    if elem is None:
        return None
    return find_local_text(elem, "ipAddress")


def _set_dns(root, idx: int, value: str) -> None:
    from .._xml import find_local
    import xml.etree.ElementTree as ET

    name = "PrimaryDNS" if idx == 1 else "SecondaryDNS"
    elem = find_local(root, name)
    if elem is None:
        elem = ET.SubElement(root, name)
        ip_el = ET.SubElement(elem, "ipAddress")
        ip_el.text = value
        return
    if not set_local_text(elem, "ipAddress", value):
        ip_el = ET.SubElement(elem, "ipAddress")
        ip_el.text = value
