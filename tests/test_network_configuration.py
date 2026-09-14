"""Network writes must preserve fields, prove acceptance and never replay."""

from types import SimpleNamespace
from unittest.mock import Mock
import xml.etree.ElementTree as ET

import pytest

from pyhikvision import IsapiClient
from pyhikvision.exceptions import HikXMLError

NS = "http://www.hikvision.com/ver20/XMLSchema"
XML = f'''<IPAddress xmlns="{NS}">
<DefaultGateway><ipAddress>192.0.2.1</ipAddress></DefaultGateway>
<ipVersion>v4</ipVersion><addressingType>static</addressingType>
<ipAddress>192.0.2.10</ipAddress><subnetMask>255.255.255.0</subnetMask>
<PrimaryDNS><ipAddress>192.0.2.53</ipAddress></PrimaryDNS>
<extension><keep>yes</keep></extension></IPAddress>'''
OK = "<ResponseStatus><statusCode>1</statusCode></ResponseStatus>"


def client(xml=XML, response=OK):
    c = IsapiClient("192.0.2.10", "test", "test", timeout=3)
    c._request = Mock(
        side_effect=[SimpleNamespace(text=xml), SimpleNamespace(text=response)]
    )
    return c


def test_read_local_address_when_gateway_precedes_it():
    with client() as c:
        state = c.get_network_config()
    assert state.ip == "192.0.2.10"
    assert state.gateway == "192.0.2.1"


def test_dhcp_only_preserves_static_values_extensions_and_namespace():
    with client() as c:
        c.set_network_config(dhcp=True)
        root = ET.fromstring(c._request.call_args.kwargs["data"])
    assert root.tag == f"{{{NS}}}IPAddress"
    assert root.find(f"{{{NS}}}addressingType").text == "dynamic"
    assert root.find(f"{{{NS}}}ipAddress").text == "192.0.2.10"
    assert root.find(f"{{{NS}}}extension/{{{NS}}}keep").text == "yes"
    assert c._request.call_count == 2


def test_static_change_never_overwrites_nested_gateway_as_local_ip():
    with client() as c:
        c.set_network_config(
            ip="192.0.2.20", mask="255.255.255.0", gateway="192.0.2.2", dhcp=False
        )
        root = ET.fromstring(c._request.call_args.kwargs["data"])
    assert root.find(f"{{{NS}}}ipAddress").text == "192.0.2.20"
    assert root.find(f"{{{NS}}}DefaultGateway/{{{NS}}}ipAddress").text == "192.0.2.2"
    assert root.find(f"{{{NS}}}PrimaryDNS/{{{NS}}}ipAddress").text == "192.0.2.53"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"ip": "::1"},
        {"dns1": "invalid"},
        {"mask": "255.0.255.0"},
        {"dhcp": "false"},
        {},
    ],
)
def test_invalid_input_causes_no_io(kwargs):
    with client() as c, pytest.raises(ValueError):
        c.set_network_config(**kwargs)
    c._request.assert_not_called()


def test_missing_mode_does_not_silently_succeed():
    with client(XML.replace("<addressingType>static</addressingType>", "")) as c:
        with pytest.raises(HikXMLError):
            c.set_network_config(dhcp=True)
    assert c._request.call_count == 1


@pytest.mark.parametrize(
    "response",
    ["<ResponseStatus><statusCode>4</statusCode></ResponseStatus>", "<html/>", ""],
)
def test_http_success_does_not_hide_vendor_rejection(response):
    with client(response=response) as c, pytest.raises(HikXMLError):
        c.set_network_config(dhcp=True)
    assert c._request.call_count == 2


def test_timeout_after_put_is_never_replayed():
    with client() as c:
        c._request.side_effect = [SimpleNamespace(text=XML), TimeoutError("lost reply")]
        with pytest.raises(TimeoutError):
            c.set_network_config(dhcp=True)
    assert c._request.call_count == 2
