"""Smoke tests — import surface only (no live device contact)."""

import pyhikvision


def test_public_api():
    assert pyhikvision.__version__
    assert hasattr(pyhikvision, "HikClient")
    assert hasattr(pyhikvision, "IsapiClient")
    assert hasattr(pyhikvision, "batch_set_ip")
    assert hasattr(pyhikvision, "DeviceInfo")
    assert hasattr(pyhikvision, "NetworkConfig")


def test_xml_helpers_namespace_strip():
    from pyhikvision._xml import parse, find_local_text, set_local_text, to_xml

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<IPAddress xmlns="http://www.hikvision.com/ver20/XMLSchema" version="2.0">'
        "<ipVersion>v4</ipVersion>"
        "<addressingType>static</addressingType>"
        "<ipAddress>192.168.1.64</ipAddress>"
        "<subnetMask>255.255.255.0</subnetMask>"
        "<DefaultGateway><ipAddress>192.168.1.1</ipAddress></DefaultGateway>"
        "<PrimaryDNS><ipAddress>8.8.8.8</ipAddress></PrimaryDNS>"
        "</IPAddress>"
    )
    root = parse(xml)
    assert find_local_text(root, "ipAddress") == "192.168.1.64"
    assert find_local_text(root, "subnetMask") == "255.255.255.0"
    assert set_local_text(root, "ipAddress", "10.40.24.101")
    out = to_xml(root)
    assert "10.40.24.101" in out
    assert "ns0:" not in out


def test_netsdk_unavailable_raises_clearly():
    import pytest
    from pyhikvision.netsdk import NetSdkClient, is_available

    if is_available():
        pytest.skip("HCNetSDK is available on this host")
    with pytest.raises(NotImplementedError):
        NetSdkClient("1.2.3.4", "admin", "x")
