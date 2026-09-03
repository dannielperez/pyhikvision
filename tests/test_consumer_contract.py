"""Consumer-contract tests for pyhikvision's public API (roadmap L3, issue #1452).

Pins the exact names and exception hierarchy that
``uniqueos/devices/services/hikvision_sdk.py`` re-exports (the read-first
boundary seam), and replays a recorded ISAPI ``deviceInfo`` fixture through
the real parser. All transport is in-process; no live device is contacted.

See ``fixtures/consumer_contracts/README.md`` for fixture provenance.
"""

from __future__ import annotations

from pathlib import Path

import pyhikvision
from pyhikvision import (
    ChannelInfo,
    DeviceInfo,
    HikAuthError,
    HikClient,
    HikError,
    HikHTTPError,
    HikUnreachableError,
    HikXMLError,
    NetworkConfig,
)
from pyhikvision.isapi.client import IsapiClient

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "consumer_contracts"


def _xml_fixture(name: str) -> str:
    return (FIXTURE_DIR / name).read_text(encoding="utf-8")


class _Resp:
    def __init__(self, text: str = "", status: int = 200) -> None:
        self.text = text
        self.status_code = status

    def close(self) -> None:
        pass


class TestPublicApiContract:
    """Pin the exact names and error hierarchy consumed by hikvision_sdk.py."""

    def test_boundary_critical_names_are_exported(self) -> None:
        required = {
            "HikClient",
            "DeviceInfo",
            "ChannelInfo",
            "NetworkConfig",
            "HikError",
            "HikAuthError",
            "HikHTTPError",
            "HikXMLError",
            "HikUnreachableError",
        }
        assert required <= set(pyhikvision.__all__)
        assert all(getattr(pyhikvision, name) is not None for name in required)

    def test_auth_error_extends_base_error(self) -> None:
        assert issubclass(HikAuthError, HikError)

    def test_http_error_extends_base_error(self) -> None:
        assert issubclass(HikHTTPError, HikError)

    def test_xml_error_extends_base_error(self) -> None:
        assert issubclass(HikXMLError, HikError)

    def test_unreachable_error_extends_base_error(self) -> None:
        assert issubclass(HikUnreachableError, HikError)


class TestDeviceInfoReplay:
    """Replay a recorded ``/ISAPI/System/deviceInfo`` body through device_info()."""

    def test_device_info_replay_returns_typed_dto(self, monkeypatch) -> None:
        client = IsapiClient("device.example.invalid", "operator", "synthetic-password")
        recorded = _xml_fixture("device_info.xml")
        monkeypatch.setattr(
            client,
            "_request",
            lambda method, path, **kw: _Resp(text=recorded),
        )

        info = client.device_info()

        assert isinstance(info, DeviceInfo)
        assert info.device_name == "Entrance NVR"
        assert info.model == "DS-7616NI-K2"
        assert info.mac_address == "ac:cf:85:00:11:22"
        assert info.device_type == "NVR"

    def test_malformed_xml_raises_typed_error(self, monkeypatch) -> None:
        client = IsapiClient("device.example.invalid", "operator", "synthetic-password")
        monkeypatch.setattr(
            client,
            "_request",
            lambda method, path, **kw: _Resp(text="not xml"),
        )

        try:
            client.device_info()
        except HikXMLError:
            pass
        else:
            raise AssertionError("expected HikXMLError on malformed deviceInfo body")


class TestErrorMappingReplay:
    """Pin the HTTP-status-to-exception mapping the adapter relies on to catch errors."""

    def test_non_2xx_response_raises_http_error(self, monkeypatch) -> None:
        client = IsapiClient("device.example.invalid", "operator", "synthetic-password")

        def fake_session_request(*args, **kwargs):
            return _Resp(text="server error", status=500)

        monkeypatch.setattr(client._session, "request", fake_session_request)

        try:
            client.device_info()
        except HikHTTPError as exc:
            assert exc.status == 500
        else:
            raise AssertionError("expected HikHTTPError on a 500 response")

    def test_repeated_401_raises_auth_error(self, monkeypatch) -> None:
        client = IsapiClient("device.example.invalid", "operator", "synthetic-password")

        def fake_session_request(*args, **kwargs):
            return _Resp(text="unauthorized", status=401)

        monkeypatch.setattr(client._session, "request", fake_session_request)

        try:
            client.device_info()
        except HikAuthError:
            pass
        else:
            raise AssertionError("expected HikAuthError when both auth schemes fail")


class TestFacadeConstruction:
    """Pin the HikClient() keyword contract the boundary/adapter relies on."""

    def test_client_accepts_the_adapter_keyword_contract(self) -> None:
        client = HikClient(
            "device.example.invalid",
            "operator",
            "synthetic-password",
            backend="isapi",
            port=443,
            scheme="https",
        )
        assert isinstance(client, HikClient)

    def test_channel_info_and_network_config_are_constructible(self) -> None:
        # Pin the DTO shapes hikvision_sdk.py re-exports: ChannelInfo requires only
        # its id, NetworkConfig is fully default-safe — no adapter-side special-casing.
        assert ChannelInfo(id=1) is not None
        assert NetworkConfig() is not None
