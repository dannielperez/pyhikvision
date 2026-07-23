"""ISAPI user / password management — offline unit tests.

Drives :class:`pyhikvision.isapi.client.IsapiClient` with ``_request`` stubbed
so no device is contacted. Asserts the resolved target user, the exact PUT
path/body (namespace preserved, element order id→userName→password, XML-escaped
secret), and the selection/precondition failure modes.
"""

import pytest

from pyhikvision.exceptions import HikError, HikXMLError
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


class _Resp:
    def __init__(self, text="", status=200):
        self.text = text
        self.status_code = status


def _client(monkeypatch, users_xml=USERS_XML, user="admin"):
    """Return an IsapiClient whose _request is stubbed; `calls` records traffic."""
    calls: list[tuple] = []

    def fake_request(self, method, path, *, data=None, timeout=None):
        calls.append((method, path, data))
        if method == "GET":
            return _Resp(users_xml)
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


def test_set_user_password_puts_expected_body(monkeypatch):
    client, calls = _client(monkeypatch)
    client.set_user_password("NewPass123")

    method, path, data = calls[-1]
    assert method == "PUT"
    assert path == "/ISAPI/Security/users/1"
    # Namespace preserved (firmwares reject a mismatched/absent xmlns).
    assert 'xmlns="http://www.std-cgi.com/ver20/XMLSchema"' in data
    # Correct element order: id, userName, password.
    assert data.index("<id>1</id>") < data.index("<userName>admin</userName>")
    assert data.index("<userName>admin</userName>") < data.index("<password>")
    assert "<password>NewPass123</password>" in data


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
