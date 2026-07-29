"""ISAPI user / password management — offline unit tests.

Drives :class:`pyhikvision.isapi.client.IsapiClient` with ``_request`` stubbed
so no device is contacted. Asserts the resolved target user, the exact PUT
path/body (namespace preserved, element order id→userName→password, XML-escaped
secret), and the selection/precondition failure modes.
"""

import pytest

from pyhikvision.exceptions import (
    HikError,
    HikHTTPError,
    HikUnsupportedPasswordEncodingError,
    HikXMLError,
)
from pyhikvision.isapi.client import IsapiClient

# Real shape captured from an OEM Hik firmware (std-cgi namespace, single admin).
USERS_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<UserList version="2.0" xmlns="http://www.std-cgi.com/ver20/XMLSchema">'
    '<User version="2.0" xmlns="http://www.std-cgi.com/ver20/XMLSchema">'
    "<id>1</id><userName>admin</userName><userLevel>Administrator</userLevel>"
    "</User></UserList>"
)

TWO_USERS_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<UserList version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
    '<User><id>1</id><userName>admin</userName><userLevel>Administrator</userLevel></User>'
    '<User><id>2</id><userName>ops</userName><userLevel>Operator</userLevel></User>'
    "</UserList>"
)

SECURITY_CAPABILITIES_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<SecurityCap version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
    "<securityVersion>0</securityVersion>"
    "<LoginPasswordLenLimit>16</LoginPasswordLenLimit>"
    "</SecurityCap>"
)

SALTED_SECURITY_CAPABILITIES_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<SecurityCap version="2.0" xmlns="http://www.hikvision.com/ver20/XMLSchema">'
    "<securityVersion>2</securityVersion>"
    "</SecurityCap>"
)


class _Resp:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status


def _client(
    monkeypatch,
    users_xml=USERS_XML,
    user="admin",
    security_capabilities_xml=SECURITY_CAPABILITIES_XML,
    capabilities_error=None,
    put_error=None,
):
    """Return an IsapiClient whose _request is stubbed; `calls` records traffic."""
    calls: list[tuple] = []

    def fake_request(self, method, path, *, data=None, timeout=None):
        calls.append((method, path, data))
        if path == "/ISAPI/Security/capabilities":
            if capabilities_error is not None:
                raise capabilities_error
            return _Resp(security_capabilities_xml)
        if path == "/ISAPI/Security/users":
            return _Resp(users_xml)
        if method == "PUT" and put_error is not None:
            raise put_error
        return _Resp("", 200)

    monkeypatch.setattr(IsapiClient, "_request", fake_request)
    client = IsapiClient("10.0.0.5", user, "oldpass")
    return client, calls


def test_get_users_parses_list(monkeypatch):
    client, _ = _client(monkeypatch, TWO_USERS_XML)
    users = client.get_users()
    assert users == [
        {"id": "1", "user_name": "admin", "user_level": "Administrator"},
        {"id": "2", "user_name": "ops", "user_level": "Operator"},
    ]


def test_get_security_capabilities_parses_password_fields(monkeypatch):
    client, calls = _client(monkeypatch)

    capabilities = client.get_security_capabilities()

    assert capabilities == {
        "securityVersion": "0",
        "LoginPasswordLenLimit": 16,
    }
    assert calls == [("GET", "/ISAPI/Security/capabilities", None)]


def test_get_security_capabilities_missing_security_version_is_none(monkeypatch):
    capabilities_xml = (
        '<SecurityCap xmlns="http://www.std-cgi.com/ver20/XMLSchema">'
        "<LoginPasswordLenLimit>12</LoginPasswordLenLimit>"
        "</SecurityCap>"
    )
    client, _ = _client(
        monkeypatch,
        security_capabilities_xml=capabilities_xml,
    )

    capabilities = client.get_security_capabilities()

    assert capabilities["securityVersion"] is None
    assert capabilities["LoginPasswordLenLimit"] == 12


def test_successful_password_rotation_never_requests_capabilities(monkeypatch):
    client, calls = _client(
        monkeypatch,
        security_capabilities_xml=SALTED_SECURITY_CAPABILITIES_XML,
    )

    client.set_user_password("NewPass123")

    assert [(method, path) for method, path, _ in calls] == [
        ("GET", "/ISAPI/Security/users"),
        ("PUT", "/ISAPI/Security/users/1"),
    ]
    assert not any(path == "/ISAPI/Security/capabilities" for _, path, _ in calls)


def test_rejected_put_with_salted_capability_raises_actionable_error(monkeypatch):
    original = HikHTTPError(
        400,
        "http://10.0.0.5/ISAPI/Security/users/1",
    )
    client, calls = _client(
        monkeypatch,
        security_capabilities_xml=SALTED_SECURITY_CAPABILITIES_XML,
        put_error=original,
    )

    with pytest.raises(
        HikUnsupportedPasswordEncodingError,
        match="out-of-band vendor tool",
    ) as caught:
        client.set_user_password("NewPass123")

    assert caught.value.__cause__ is original
    assert [(method, path) for method, path, _ in calls] == [
        ("GET", "/ISAPI/Security/users"),
        ("PUT", "/ISAPI/Security/users/1"),
        ("GET", "/ISAPI/Security/capabilities"),
    ]


def test_rejected_put_without_salted_capability_reraises_original(monkeypatch):
    original = HikHTTPError(
        400,
        "http://10.0.0.5/ISAPI/Security/users/1",
    )
    client, calls = _client(
        monkeypatch,
        put_error=original,
    )

    with pytest.raises(HikHTTPError) as caught:
        client.set_user_password("NewPass123")

    assert caught.value is original
    assert [(method, path) for method, path, _ in calls] == [
        ("GET", "/ISAPI/Security/users"),
        ("PUT", "/ISAPI/Security/users/1"),
        ("GET", "/ISAPI/Security/capabilities"),
    ]


def test_rejected_put_with_capability_endpoint_error_reraises_original(monkeypatch):
    original = HikHTTPError(
        400,
        "http://10.0.0.5/ISAPI/Security/users/1",
    )
    client, calls = _client(
        monkeypatch,
        capabilities_error=HikHTTPError(
            404,
            "http://10.0.0.5/ISAPI/Security/capabilities",
        ),
        put_error=original,
    )

    with pytest.raises(HikHTTPError) as caught:
        client.set_user_password("NewPass123")

    assert caught.value is original
    assert [(method, path) for method, path, _ in calls] == [
        ("GET", "/ISAPI/Security/users"),
        ("PUT", "/ISAPI/Security/users/1"),
        ("GET", "/ISAPI/Security/capabilities"),
    ]


@pytest.mark.parametrize("lookup_result", [{}, RuntimeError("lookup failed")])
def test_rejected_put_with_unusable_classification_reraises_original(
    monkeypatch,
    lookup_result,
):
    original = HikHTTPError(
        400,
        "http://10.0.0.5/ISAPI/Security/users/1",
    )
    client, _ = _client(monkeypatch, put_error=original)

    def fake_capabilities():
        if isinstance(lookup_result, Exception):
            raise lookup_result
        return lookup_result

    monkeypatch.setattr(client, "get_security_capabilities", fake_capabilities)

    with pytest.raises(HikHTTPError) as caught:
        client.set_user_password("NewPass123")

    assert caught.value is original


def test_set_user_password_puts_expected_body(monkeypatch):
    client, calls = _client(monkeypatch)
    client.set_user_password("NewPass123")

    method, path, data = calls[-1]
    assert method == "PUT"
    assert path == "/ISAPI/Security/users/1"
    assert data == (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<User version="2.0" xmlns="http://www.std-cgi.com/ver20/XMLSchema">'
        "<id>1</id>"
        "<userName>admin</userName>"
        "<password>NewPass123</password>"
        "</User>"
    )


def test_password_is_xml_escaped(monkeypatch):
    client, calls = _client(monkeypatch)
    client.set_user_password('a<b>&"c')
    _, _, data = calls[-1]
    # Metacharacters entity-encoded so the secret can't break out of <password>.
    assert '<password>a&lt;b&gt;&amp;"c</password>' in data
    inner = data.split("<password>", 1)[1].split("</password>", 1)[0]
    assert "<" not in inner
    assert ">" not in inner


def test_selects_named_user(monkeypatch):
    client, calls = _client(monkeypatch, TWO_USERS_XML)
    client.set_user_password("x", user_name="ops")
    _, path, data = calls[-1]
    assert path == "/ISAPI/Security/users/2"
    assert "<userName>ops</userName>" in data


def test_selects_by_id(monkeypatch):
    client, calls = _client(monkeypatch, TWO_USERS_XML)
    client.set_user_password("x", user_id="2")
    _, path, _ = calls[-1]
    assert path == "/ISAPI/Security/users/2"


def test_defaults_to_authenticating_user(monkeypatch):
    # Client logs in as "ops"; with no selector it should target ops, not the
    # first-listed admin.
    client, calls = _client(monkeypatch, TWO_USERS_XML, user="ops")
    client.set_user_password("x")
    _, path, _ = calls[-1]
    assert path == "/ISAPI/Security/users/2"


def test_unknown_user_raises(monkeypatch):
    client, _ = _client(monkeypatch, TWO_USERS_XML)
    with pytest.raises(HikError):
        client.set_user_password("x", user_name="ghost")


def test_malformed_users_xml_raises(monkeypatch):
    client, _ = _client(monkeypatch, "not xml <<<")
    with pytest.raises(HikXMLError):
        client.set_user_password("x")
