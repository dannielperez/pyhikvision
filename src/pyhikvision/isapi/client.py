"""High-level Hikvision ISAPI client.

Pure-Python HTTP(S) + Digest auth. Works wherever ``requests`` works,
including over WireGuard / routed links. No native SDK required.

Endpoints implemented (sufficient for IP-migration workflows):

- GET  /ISAPI/System/deviceInfo
- GET  /ISAPI/System/Network/interfaces/{n}/ipAddress
- PUT  /ISAPI/System/Network/interfaces/{n}/ipAddress
- PUT  /ISAPI/System/reboot
- GET  /ISAPI/Security/users
- PUT  /ISAPI/Security/users/{id}

Reference: Hikvision ISAPI 2.x specification (publicly distributed under
"Hikvision ISAPI Open Platform Network Communication Specification").
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from typing import Optional
from xml.sax.saxutils import escape

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth
from requests.exceptions import (
    ConnectionError as RequestsConnectionError,
    Timeout as RequestsTimeout,
)

from .._xml import find_local_text, localname, parse, set_local_text, to_xml
from ..exceptions import (
    HikAuthError,
    HikError,
    HikHTTPError,
    HikUnreachableError,
    HikXMLError,
)
from ..models import DeviceInfo, LineDetectionConfig, NetworkConfig

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
            set_local_text(root, "addressingType", "dynamic" if dhcp else "static")

        body = to_xml(root)
        self._request("PUT", path, data=body)

    # ---- smart events ----
    def get_line_detection(
        self, *, channel_id: int = 1, line_id: int = 1
    ) -> LineDetectionConfig:
        """Return one line-crossing rule from a camera's ISAPI config."""
        path = f"/ISAPI/Smart/LineDetection/{channel_id}"
        resp = self._request("GET", path)
        return _parse_line_detection(resp.text, channel_id=channel_id, line_id=line_id)

    def set_line_detection(
        self,
        *,
        channel_id: int = 1,
        line_id: int = 1,
        enabled: Optional[bool] = None,
        sensitivity: Optional[int] = None,
        direction: Optional[str] = None,
        start: Optional[tuple[int, int]] = None,
        end: Optional[tuple[int, int]] = None,
        verify: bool = True,
    ) -> LineDetectionConfig:
        """Safely update one line-crossing rule with read-back verification.

        The current XML is read and modified in place so undocumented,
        firmware-specific elements survive the PUT. Coordinates are expressed
        in the device's normalized screen space (commonly 1000 by 1000).
        """
        if channel_id < 1 or line_id < 1:
            raise ValueError("channel_id and line_id must be positive")
        if enabled is not None and not isinstance(enabled, bool):
            raise ValueError("enabled must be a boolean")
        if (start is None) != (end is None):
            raise ValueError("start and end must be supplied together")
        if sensitivity is not None and not 1 <= sensitivity <= 100:
            raise ValueError("sensitivity must be between 1 and 100")
        allowed_directions = {"any", "left-right", "right-left"}
        if direction is not None and direction not in allowed_directions:
            raise ValueError("direction must be one of: any, left-right, right-left")

        path = f"/ISAPI/Smart/LineDetection/{channel_id}"
        cur = self._request("GET", path)
        current = _parse_line_detection(
            cur.text, channel_id=channel_id, line_id=line_id
        )
        if current.multi_scene_supported:
            raise NotImplementedError(
                "multi-scene LineDetection requires the separate lineDetectionItem endpoint"
            )
        desired_enabled = current.enabled if enabled is None else enabled
        desired_sensitivity = (
            current.sensitivity if sensitivity is None else sensitivity
        )
        desired_direction = current.direction if direction is None else direction
        desired_start = current.start if start is None else start
        desired_end = current.end if end is None else end
        _validate_point(
            "start", desired_start, current.screen_width, current.screen_height
        )
        _validate_point("end", desired_end, current.screen_width, current.screen_height)
        if desired_enabled and desired_start == desired_end:
            raise ValueError("an enabled line must use two different points")

        desired_global = desired_enabled

        desired = (
            desired_enabled,
            desired_global,
            desired_sensitivity,
            desired_direction,
            desired_start,
            desired_end,
        )
        actual = (
            current.enabled,
            current.global_enabled,
            current.sensitivity,
            current.direction,
            current.start,
            current.end,
        )
        if desired == actual:
            return current

        try:
            root = parse(cur.text)
        except Exception as exc:
            raise HikXMLError(f"LineDetection (pre-PUT) not XML: {exc}") from exc
        global_enabled = _direct_child(root, "enabled")
        line = _find_line_item(root, line_id)
        if global_enabled is None or line is None:
            raise HikXMLError("LineDetection response is missing required elements")
        _set_direct_text(global_enabled, str(desired_global).lower())
        _require_direct_text(line, "sensitivityLevel", str(desired_sensitivity))
        _require_direct_text(line, "directionSensitivity", desired_direction)
        coordinates = _coordinates(line)
        if len(coordinates) < 2:
            raise HikXMLError("LineItem must contain at least two Coordinates")
        _set_coordinate(coordinates[0], desired_start)
        _set_coordinate(coordinates[1], desired_end)

        self._request("PUT", path, data=to_xml(root))
        if not verify:
            return LineDetectionConfig(
                channel_id=channel_id,
                line_id=line_id,
                enabled=desired_enabled,
                global_enabled=desired_global,
                item_enabled=current.item_enabled,
                multi_scene_supported=False,
                sensitivity=desired_sensitivity,
                direction=desired_direction,
                start=desired_start,
                end=desired_end,
                screen_width=current.screen_width,
                screen_height=current.screen_height,
            )

        verified = self.get_line_detection(channel_id=channel_id, line_id=line_id)
        verified_values = (
            verified.enabled,
            verified.global_enabled,
            verified.sensitivity,
            verified.direction,
            verified.start,
            verified.end,
        )
        if verified_values != desired:
            raise HikXMLError(
                "LineDetection read-back does not match the requested config"
            )
        return verified

    # ---- power ----
    def reboot(self) -> None:
        try:
            self._request("PUT", "/ISAPI/System/reboot", timeout=15.0)
        except HikUnreachableError:
            # Reboot frequently drops the connection mid-response; tolerate.
            return

    # ---- user / password management ----
    def get_users(self) -> list[dict]:
        """Return the device's user accounts from GET /ISAPI/Security/users.

        Each entry is ``{"id", "user_name", "user_level"}`` (password is never
        returned by the device). Namespace-agnostic parse, so it works across
        the ``hikvision.com`` and ``std-cgi.com`` (OEM) schema variants.
        """
        resp = self._request("GET", "/ISAPI/Security/users")
        try:
            root = parse(resp.text)
        except Exception as exc:
            raise HikXMLError(f"users list not XML: {exc}") from exc
        users: list[dict] = []
        for el in root.iter():
            if localname(el.tag) == "User":
                users.append(
                    {
                        "id": find_local_text(el, "id"),
                        "user_name": find_local_text(el, "userName"),
                        "user_level": find_local_text(el, "userLevel"),
                    }
                )
        return users

    def set_user_password(
        self,
        new_password: str,
        *,
        user_name: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> None:
        """Change an account's password via PUT /ISAPI/Security/users/{id}.

        The target user is resolved from ``GET /ISAPI/Security/users`` by, in
        order: explicit ``user_id``, explicit ``user_name``, the account this
        client authenticates as, or — when the device has exactly one account —
        that sole user. The PUT authenticates with the client's *current*
        credentials, so with no selector this rotates the logged-in account's
        own password.

        The new password is sent in plaintext over the (digest-authenticated)
        ISAPI channel, matching Hikvision's default security model. Firmwares
        that *mandate* the salted "security version" upload
        (``/ISAPI/Security/userCheck`` challenge) are not yet supported and
        will reject the change with :class:`HikHTTPError`. Some OEM firmwares
        also cap password length (e.g. ``SecurityCap/LoginPasswordLenLimit``);
        an over-long secret is likewise rejected by the device, not here.
        """
        resp = self._request("GET", "/ISAPI/Security/users")
        try:
            root = parse(resp.text)
        except Exception as exc:
            raise HikXMLError(f"users list not XML: {exc}") from exc

        target = self._select_user(root, user_name=user_name, user_id=user_id)
        if target is None:
            raise HikError(
                f"user not found (user_name={user_name!r}, user_id={user_id!r})"
            )
        uid = find_local_text(target, "id")
        uname = find_local_text(target, "userName")
        if not uid or not uname:
            raise HikXMLError("user entry missing <id>/<userName>")

        # Preserve the device's exact namespace on the PUT — Hikvision firmwares
        # (and OEM std-cgi variants) reject a mismatched/absent xmlns. Build the
        # body explicitly to control element order (id, userName, password).
        ns = _namespace_of(root.tag) or "http://www.hikvision.com/ver20/XMLSchema"
        body = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<User version="2.0" xmlns="{ns}">'
            f"<id>{escape(uid)}</id>"
            f"<userName>{escape(uname)}</userName>"
            f"<password>{escape(new_password)}</password>"
            "</User>"
        )
        self._request("PUT", f"/ISAPI/Security/users/{uid}", data=body)

    def _select_user(self, root, *, user_name=None, user_id=None):
        """Pick the target <User> element from a parsed UserList."""
        users = [el for el in root.iter() if localname(el.tag) == "User"]
        if user_id is not None:
            return next(
                (el for el in users if find_local_text(el, "id") == str(user_id)),
                None,
            )
        if user_name is not None:
            return next(
                (el for el in users if find_local_text(el, "userName") == user_name),
                None,
            )
        own = next(
            (el for el in users if find_local_text(el, "userName") == self.user),
            None,
        )
        if own is not None:
            return own
        return users[0] if len(users) == 1 else None


def _namespace_of(tag: str) -> str:
    """Extract the ``{ns}`` prefix from an ElementTree tag, or ``""``."""
    if tag.startswith("{"):
        return tag[1:].split("}", 1)[0]
    return ""


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


# --- helpers for LineDetection XML -------------------------------------


def _direct_child(elem: ET.Element, name: str) -> Optional[ET.Element]:
    for child in elem:
        if localname(child.tag) == name:
            return child
    return None


def _direct_text(elem: ET.Element, name: str) -> Optional[str]:
    child = _direct_child(elem, name)
    if child is None or child.text is None:
        return None
    return child.text.strip() or None


def _set_direct_text(elem: ET.Element, value: str) -> None:
    elem.text = value


def _require_direct_text(elem: ET.Element, name: str, value: str) -> None:
    child = _direct_child(elem, name)
    if child is None:
        raise HikXMLError(f"LineDetection element missing: {name}")
    child.text = value


def _find_line_item(root: ET.Element, line_id: int) -> Optional[ET.Element]:
    for elem in root.iter():
        if localname(elem.tag) != "LineItem":
            continue
        if _direct_text(elem, "id") == str(line_id):
            return elem
    return None


def _coordinates(line: ET.Element) -> list[ET.Element]:
    return [elem for elem in line.iter() if localname(elem.tag) == "Coordinates"]


def _coordinate(elem: ET.Element) -> tuple[int, int]:
    x = _direct_text(elem, "positionX")
    y = _direct_text(elem, "positionY")
    if x is None or y is None:
        raise HikXMLError("Coordinates missing positionX or positionY")
    try:
        return int(x), int(y)
    except ValueError as exc:
        raise HikXMLError("Coordinates must be integers") from exc


def _set_coordinate(elem: ET.Element, point: tuple[int, int]) -> None:
    _require_direct_text(elem, "positionX", str(point[0]))
    _require_direct_text(elem, "positionY", str(point[1]))


def _parse_bool(value: Optional[str], *, field: str) -> bool:
    if value == "true":
        return True
    if value == "false":
        return False
    raise HikXMLError(f"LineDetection {field} must be true or false")


def _parse_required_int(elem: ET.Element, name: str) -> int:
    value = _direct_text(elem, name)
    if value is None:
        raise HikXMLError(f"LineDetection element missing: {name}")
    try:
        return int(value)
    except ValueError as exc:
        raise HikXMLError(f"LineDetection {name} must be an integer") from exc


def _parse_descendant_required_int(elem: ET.Element, name: str) -> int:
    value = find_local_text(elem, name)
    if value is None:
        raise HikXMLError(f"LineDetection element missing: {name}")
    try:
        return int(value)
    except ValueError as exc:
        raise HikXMLError(f"LineDetection {name} must be an integer") from exc


def _parse_line_detection(
    xml: str, *, channel_id: int, line_id: int
) -> LineDetectionConfig:
    try:
        root = parse(xml)
    except Exception as exc:
        raise HikXMLError(f"LineDetection not XML: {exc}") from exc
    line = _find_line_item(root, line_id)
    if line is None:
        raise HikXMLError(f"LineDetection line id {line_id} not found")
    points = _coordinates(line)
    if len(points) < 2:
        raise HikXMLError("LineItem must contain at least two Coordinates")
    direction = _direct_text(line, "directionSensitivity")
    if direction is None:
        raise HikXMLError("LineDetection directionSensitivity is missing")
    global_enabled = _parse_bool(_direct_text(root, "enabled"), field="global enabled")
    item_enabled = _parse_bool(_direct_text(line, "enabled"), field="item enabled")
    multi_scene_supported = _parse_bool(
        find_local_text(root, "isSupportMultiScene"),
        field="isSupportMultiScene",
    )
    return LineDetectionConfig(
        channel_id=channel_id,
        line_id=line_id,
        enabled=global_enabled and (item_enabled if multi_scene_supported else True),
        global_enabled=global_enabled,
        item_enabled=item_enabled,
        multi_scene_supported=multi_scene_supported,
        sensitivity=_parse_required_int(line, "sensitivityLevel"),
        direction=direction,
        start=_coordinate(points[0]),
        end=_coordinate(points[1]),
        screen_width=_parse_descendant_required_int(root, "normalizedScreenWidth"),
        screen_height=_parse_descendant_required_int(root, "normalizedScreenHeight"),
        raw_xml=xml,
    )


def _validate_point(name: str, point: tuple[int, int], width: int, height: int) -> None:
    if (
        not isinstance(point, tuple)
        or len(point) != 2
        or any(isinstance(value, bool) or not isinstance(value, int) for value in point)
    ):
        raise ValueError(f"{name} must be a pair of integers")
    x, y = point
    if not 0 <= x <= width or not 0 <= y <= height:
        raise ValueError(
            f"{name} must be within normalized screen bounds {width}x{height}"
        )
