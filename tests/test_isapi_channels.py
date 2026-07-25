"""ISAPI channel enumeration — offline unit tests.

Drives :class:`pyhikvision.isapi.client.IsapiClient` with ``_request`` stubbed
so no device is contacted. Asserts the requested paths, the typed rows, both
XML namespaces seen in the field, the status merge, and every degradation path.

Fixture bodies follow the Hikvision ISAPI 2.x specification (the same reference
the rest of this client is built against). They are spec-shaped, not captured
from one firmware, so the parser is deliberately namespace-agnostic and
tolerant of absent optional elements.
"""

import pytest

from pyhikvision.exceptions import HikHTTPError, HikXMLError
from pyhikvision.isapi.client import IsapiClient
from pyhikvision.models import ChannelInfo

# Hikvision namespace, two adopted IP cameras.
INPUT_PROXY_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<InputProxyChannelList version="2.0" '
    'xmlns="http://www.hikvision.com/ver20/XMLSchema">'
    "<InputProxyChannel><id>1</id><name>Tablilla Visita</name>"
    "<sourceInputPortDescriptor><proxyProtocol>ONVIF</proxyProtocol>"
    "<ipAddress>10.40.25.11</ipAddress><managePortNo>80</managePortNo>"
    "<srcInputPort>1</srcInputPort></sourceInputPortDescriptor>"
    "</InputProxyChannel>"
    "<InputProxyChannel><id>2</id><name>Cara Visitante</name>"
    "<sourceInputPortDescriptor><proxyProtocol>HIKVISION</proxyProtocol>"
    "<ipAddress>10.40.25.12</ipAddress><managePortNo>8000</managePortNo>"
    "<srcInputPort>1</srcInputPort></sourceInputPortDescriptor>"
    "</InputProxyChannel>"
    "</InputProxyChannelList>"
)

# OEM std-cgi namespace — the other spelling this client already handles.
INPUT_PROXY_STD_CGI_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<InputProxyChannelList version="2.0" '
    'xmlns="http://www.std-cgi.com/ver20/XMLSchema">'
    "<InputProxyChannel><id>7</id><name>Peatonal</name>"
    "<sourceInputPortDescriptor><ipAddress>10.40.25.17</ipAddress>"
    "</sourceInputPortDescriptor></InputProxyChannel>"
    "</InputProxyChannelList>"
)

STATUS_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<InputProxyChannelStatusList version="2.0" '
    'xmlns="http://www.hikvision.com/ver20/XMLSchema">'
    "<InputProxyChannelStatus><id>1</id><online>true</online>"
    "</InputProxyChannelStatus>"
    "<InputProxyChannelStatus><id>2</id><online>false</online>"
    "</InputProxyChannelStatus>"
    "</InputProxyChannelStatusList>"
)

VIDEO_INPUT_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<VideoInputChannelList version="2.0" '
    'xmlns="http://www.hikvision.com/ver20/XMLSchema">'
    "<VideoInputChannel><id>1</id><name>Local 1</name></VideoInputChannel>"
    "</VideoInputChannelList>"
)


class _Resp:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status


def _client(monkeypatch, routes):
    """Stub _request with a path->body (or path->Exception) routing table."""
    calls = []

    def fake_request(self, method, path, *, data=None, timeout=None):
        calls.append((method, path, timeout))
        for prefix, outcome in routes.items():
            if path == prefix:
                if isinstance(outcome, Exception):
                    raise outcome
                return _Resp(outcome)
        raise HikHTTPError(404, path, "not found")

    monkeypatch.setattr(IsapiClient, "_request", fake_request)
    client = IsapiClient("10.40.25.250", "admin", "pw")
    return client, calls


PROXY = "/ISAPI/ContentMgmt/InputProxy/channels"
STATUS = "/ISAPI/ContentMgmt/InputProxy/channels/status"
INPUTS = "/ISAPI/System/Video/inputs/channels"


def test_input_proxy_channels_returns_typed_rows(monkeypatch):
    client, calls = _client(monkeypatch, {PROXY: INPUT_PROXY_XML})

    channels = client.input_proxy_channels()

    assert [(method, path) for method, path, _ in calls] == [("GET", PROXY)]
    assert all(isinstance(c, ChannelInfo) for c in channels)
    assert [c.id for c in channels] == [1, 2]
    first = channels[0]
    assert first.name == "Tablilla Visita"
    assert first.source_ip == "10.40.25.11"
    assert first.source_port == 80
    assert first.source_channel == 1
    assert first.protocol == "ONVIF"
    assert first.kind == "input_proxy"
    # Status was not requested, so online is UNKNOWN — not False.
    assert first.online is None


def test_channel_parsing_is_namespace_agnostic(monkeypatch):
    client, _calls = _client(monkeypatch, {PROXY: INPUT_PROXY_STD_CGI_XML})

    channels = client.input_proxy_channels()

    assert [c.id for c in channels] == [7]
    assert channels[0].name == "Peatonal"
    assert channels[0].source_ip == "10.40.25.17"
    # Absent optional elements stay None rather than being invented.
    assert channels[0].source_port is None
    assert channels[0].protocol is None


def test_with_status_merges_online_flags(monkeypatch):
    client, calls = _client(
        monkeypatch,
        {PROXY: INPUT_PROXY_XML, STATUS: STATUS_XML},
    )

    channels = client.input_proxy_channels(with_status=True)

    assert [path for _m, path, _t in calls] == [PROXY, STATUS]
    assert channels[0].online is True
    assert channels[1].online is False


def test_status_failure_leaves_online_unknown(monkeypatch):
    """Enumeration must not fail because the status endpoint is missing."""
    client, _calls = _client(
        monkeypatch,
        {PROXY: INPUT_PROXY_XML, STATUS: HikHTTPError(404, STATUS, "nope")},
    )

    channels = client.input_proxy_channels(with_status=True)

    assert [c.id for c in channels] == [1, 2]
    assert all(c.online is None for c in channels)


def test_video_input_channels_returns_local_inputs(monkeypatch):
    client, calls = _client(monkeypatch, {INPUTS: VIDEO_INPUT_XML})

    channels = client.video_input_channels()

    assert [path for _m, path, _t in calls] == [INPUTS]
    assert [c.id for c in channels] == [1]
    assert channels[0].kind == "video_input"
    assert channels[0].source_ip is None


def test_channels_merges_both_families(monkeypatch):
    client, _calls = _client(
        monkeypatch,
        {PROXY: INPUT_PROXY_XML, INPUTS: VIDEO_INPUT_XML},
    )

    channels = client.channels()

    assert [(c.kind, c.id) for c in channels] == [
        ("input_proxy", 1),
        ("input_proxy", 2),
        ("video_input", 1),
    ]


def test_channels_tolerates_one_missing_family(monkeypatch):
    """A camera implements only video inputs; a recorder only input proxies."""
    client, _calls = _client(monkeypatch, {INPUTS: VIDEO_INPUT_XML})

    channels = client.channels()

    assert [(c.kind, c.id) for c in channels] == [("video_input", 1)]


def test_channels_raises_when_both_families_fail(monkeypatch):
    """A broken device must never look like a device with no cameras."""
    client, _calls = _client(monkeypatch, {})

    with pytest.raises(HikHTTPError):
        client.channels()


def test_rows_without_a_usable_id_are_skipped(monkeypatch):
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<InputProxyChannelList xmlns="http://www.hikvision.com/ver20/XMLSchema">'
        "<InputProxyChannel><name>no id</name></InputProxyChannel>"
        "<InputProxyChannel><id>abc</id><name>bad id</name></InputProxyChannel>"
        "<InputProxyChannel><id>5</id><name>good</name></InputProxyChannel>"
        "</InputProxyChannelList>"
    )
    client, _calls = _client(monkeypatch, {PROXY: body})

    channels = client.input_proxy_channels()

    assert [c.id for c in channels] == [5]
    assert channels[0].name == "good"


def test_malformed_xml_raises_a_typed_error(monkeypatch):
    client, _calls = _client(monkeypatch, {PROXY: "<not-xml"})

    with pytest.raises(HikXMLError):
        client.input_proxy_channels()


def test_empty_list_is_not_an_error(monkeypatch):
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<InputProxyChannelList xmlns="http://www.hikvision.com/ver20/XMLSchema"/>'
    )
    client, _calls = _client(monkeypatch, {PROXY: body})

    assert client.input_proxy_channels() == []


def test_explicit_timeout_is_forwarded(monkeypatch):
    client, calls = _client(
        monkeypatch,
        {PROXY: INPUT_PROXY_XML, STATUS: STATUS_XML},
    )

    client.input_proxy_channels(with_status=True, timeout=3.5)

    assert [timeout for _m, _p, timeout in calls] == [3.5, 3.5]


def test_channel_info_to_dict_drops_raw_xml():
    channel = ChannelInfo(id=1, name="x", raw_xml="<InputProxyChannel/>")

    payload = channel.to_dict()

    assert "raw_xml" not in payload
    assert payload["id"] == 1
    assert payload["kind"] == "input_proxy"
