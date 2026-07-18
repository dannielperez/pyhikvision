from types import SimpleNamespace

import pytest

from pyhikvision import IsapiClient
from pyhikvision.exceptions import HikXMLError


LINE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<LineDetection xmlns="http://www.hikvision.com/ver20/XMLSchema">
  <id>1</id><enabled>false</enabled>
  <normalizedScreenSize>
    <normalizedScreenWidth>1000</normalizedScreenWidth>
    <normalizedScreenHeight>1000</normalizedScreenHeight>
  </normalizedScreenSize>
  <LineItemList size="1"><LineItem>
    <id>1</id><enabled>false</enabled>
    <sensitivityLevel>50</sensitivityLevel>
    <directionSensitivity>any</directionSensitivity>
    <CoordinatesList>
      <Coordinates><positionX>0</positionX><positionY>1000</positionY></Coordinates>
      <Coordinates><positionX>0</positionX><positionY>1000</positionY></Coordinates>
    </CoordinatesList>
  </LineItem></LineItemList>
  <isSupportMultiScene>false</isSupportMultiScene>
  <recogRuleType>vectorMode</recogRuleType>
</LineDetection>"""


ENABLED_XML = (
    LINE_XML.replace("<enabled>false</enabled>", "<enabled>true</enabled>", 1)
    .replace(
        "<sensitivityLevel>50</sensitivityLevel>",
        "<sensitivityLevel>45</sensitivityLevel>",
    )
    .replace(
        "<positionX>0</positionX><positionY>1000</positionY>",
        "<positionX>610</positionX><positionY>590</positionY>",
        1,
    )
    .replace(
        "<positionX>0</positionX><positionY>1000</positionY>",
        "<positionX>800</positionX><positionY>1000</positionY>",
        1,
    )
)


def _client_with_responses(*xml_responses):
    client = IsapiClient("camera", "user", "password")
    calls = []
    responses = iter(xml_responses)

    def request(method, path, *, data=None, timeout=None):
        calls.append((method, path, data))
        if method == "PUT":
            return SimpleNamespace(text="")
        return SimpleNamespace(text=next(responses))

    client._request = request
    return client, calls


def test_get_line_detection_parses_namespaced_xml():
    client, _ = _client_with_responses(LINE_XML)
    config = client.get_line_detection()
    assert config.to_dict() == {
        "channel_id": 1,
        "line_id": 1,
        "enabled": False,
        "global_enabled": False,
        "item_enabled": False,
        "multi_scene_supported": False,
        "sensitivity": 50,
        "direction": "any",
        "start": (0, 1000),
        "end": (0, 1000),
        "screen_width": 1000,
        "screen_height": 1000,
    }


def test_set_line_detection_roundtrips_and_verifies():
    client, calls = _client_with_responses(LINE_XML, ENABLED_XML)
    config = client.set_line_detection(
        enabled=True,
        sensitivity=45,
        direction="any",
        start=(610, 590),
        end=(800, 1000),
    )
    assert config.enabled is True
    assert config.start == (610, 590)
    put = next(call for call in calls if call[0] == "PUT")
    assert "<enabled>true</enabled>" in put[2]
    assert "<positionX>610</positionX>" in put[2]
    assert "<isSupportMultiScene>false</isSupportMultiScene>" in put[2]


def test_set_line_detection_suppresses_noop_put():
    client, calls = _client_with_responses(ENABLED_XML)
    client.set_line_detection(
        enabled=True,
        sensitivity=45,
        direction="any",
        start=(610, 590),
        end=(800, 1000),
    )
    assert [call[0] for call in calls] == ["GET"]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"start": (1, 2)},
        {"enabled": True, "start": (2, 2), "end": (2, 2)},
        {"start": (-1, 2), "end": (3, 4)},
        {"start": (1, 2), "end": (1001, 4)},
        {"sensitivity": 0},
        {"sensitivity": 101},
        {"direction": "left"},
        {"enabled": 1},
    ],
)
def test_set_line_detection_rejects_invalid_values(kwargs):
    client, calls = _client_with_responses(LINE_XML)
    with pytest.raises(ValueError):
        client.set_line_detection(**kwargs)
    assert not any(call[0] == "PUT" for call in calls)


def test_set_line_detection_detects_readback_mismatch():
    client, _ = _client_with_responses(LINE_XML, LINE_XML)
    with pytest.raises(HikXMLError, match="read-back"):
        client.set_line_detection(enabled=True, start=(610, 590), end=(800, 1000))


def test_disabled_line_allows_degenerate_rollback_geometry():
    client, calls = _client_with_responses(ENABLED_XML, LINE_XML)
    config = client.set_line_detection(
        enabled=False,
        sensitivity=50,
        start=(0, 1000),
        end=(0, 1000),
    )
    assert config.enabled is False
    assert any(call[0] == "PUT" for call in calls)
