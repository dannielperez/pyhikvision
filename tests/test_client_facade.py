"""HikClient must expose the ISAPI surface consumers actually call.

``HikClient`` delegates explicitly — there is no ``__getattr__`` passthrough —
so any method added to ``IsapiClient`` is invisible through the facade until it
is forwarded here. Channel enumeration shipped on ``IsapiClient`` and was NOT
forwarded, so a consumer calling ``HikClient.channels()`` got an
``AttributeError`` that a caller's broad error handler would report as an
ordinary connection failure.

These tests pin the delegation itself so the facade cannot silently fall behind
the implementation again. No device is contacted.
"""

import inspect

import pytest

from pyhikvision import ChannelInfo, HikClient
from pyhikvision.isapi.client import IsapiClient

# ISAPI methods a consumer is expected to reach through the facade.
DELEGATED = [
    "device_info",
    "get_network_config",
    "set_network_config",
    "get_line_detection",
    "set_line_detection",
    "reboot",
    "get_users",
    "input_proxy_channels",
    "video_input_channels",
    "channels",
    "snapshot",
    "rtsp_url",
    "snapshot_rtsp",
]


@pytest.mark.parametrize("name", DELEGATED)
def test_facade_exposes_the_method(name):
    assert hasattr(HikClient, name), f"HikClient does not forward {name}()"


@pytest.mark.parametrize("name", DELEGATED)
def test_implementation_still_has_the_method(name):
    """A rename on IsapiClient must fail here, not at runtime in a consumer."""
    assert hasattr(IsapiClient, name), f"IsapiClient lost {name}()"


@pytest.mark.parametrize(
    "name",
    ["input_proxy_channels", "video_input_channels", "channels"],
)
def test_channel_methods_forward_their_arguments(monkeypatch, name):
    """kwargs must reach the implementation — notably the explicit timeout."""
    seen = {}

    class FakeImpl:
        def __getattr__(self, attr):
            def _call(**kwargs):
                seen["method"] = attr
                seen["kwargs"] = kwargs
                return [ChannelInfo(id=1, name="Cam")]

            return _call

    client = HikClient.__new__(HikClient)
    client._impl = FakeImpl()

    result = getattr(client, name)(timeout=3.5)

    assert seen["method"] == name
    assert seen["kwargs"]["timeout"] == 3.5
    assert isinstance(result[0], ChannelInfo)


def test_channels_forwards_with_status():
    seen = {}

    class FakeImpl:
        def channels(self, **kwargs):
            seen.update(kwargs)
            return []

    client = HikClient.__new__(HikClient)
    client._impl = FakeImpl()

    client.channels(with_status=True, timeout=9.0)

    assert seen == {"with_status": True, "timeout": 9.0}


def test_no_getattr_passthrough_hides_a_missing_delegation():
    """Documents WHY these tests exist: the facade is explicit, not dynamic."""
    assert not hasattr(HikClient, "__getattr__"), (
        "HikClient gained a __getattr__ passthrough; if that is intended, these "
        "delegation tests can be relaxed — until then every ISAPI method must be "
        "forwarded explicitly."
    )


def test_channel_return_annotation_is_the_typed_dto():
    """The facade must not degrade the typed result into a raw payload."""
    for name in ("input_proxy_channels", "video_input_channels", "channels"):
        signature = inspect.signature(getattr(HikClient, name))
        assert "ChannelInfo" in str(signature.return_annotation)
