"""Hikvision recorder JPEG and RTSP channel mapping, without device I/O."""

from __future__ import annotations

import subprocess

import pytest

from pyhikvision.exceptions import HikError, HikUnreachableError
from pyhikvision.isapi.client import IsapiClient


class _Response:
    def __init__(self, content: bytes) -> None:
        self.content = content


@pytest.mark.parametrize(
    ("channel_id", "stream", "expected"),
    [(1, "main", 101), (1, "sub", 102), (16, "main", 1601), (16, "sub", 1602)],
)
def test_streaming_channel_mapping(channel_id, stream, expected):
    assert IsapiClient._streaming_channel_id(channel_id, stream) == expected


@pytest.mark.parametrize(
    ("channel_id", "stream"),
    [(0, "main"), (-1, "sub"), (True, "main"), (1, "third")],
)
def test_streaming_channel_mapping_rejects_invalid_values(channel_id, stream):
    with pytest.raises(ValueError):
        IsapiClient._streaming_channel_id(channel_id, stream)


def test_snapshot_fetches_native_jpeg_from_exact_channel(monkeypatch):
    calls = []
    image = b"\xff\xd8jpeg\xff\xd9"

    def fake_request(self, method, path, *, data=None, timeout=None):
        calls.append((method, path, data, timeout))
        return _Response(image)

    monkeypatch.setattr(IsapiClient, "_request", fake_request)
    client = IsapiClient("10.40.31.250", "operator", "secret")

    assert client.snapshot(channel_id=16, stream="sub", timeout=4.5) == image
    assert calls == [
        ("GET", "/ISAPI/Streaming/channels/1602/picture", None, 4.5),
    ]


def test_snapshot_refuses_an_empty_response(monkeypatch):
    monkeypatch.setattr(
        IsapiClient,
        "_request",
        lambda *args, **kwargs: _Response(b""),
    )
    client = IsapiClient("10.40.31.250", "operator", "secret")

    with pytest.raises(HikError, match="returned no image"):
        client.snapshot(channel_id=6)


def test_rtsp_url_encodes_credentials_and_custom_port():
    client = IsapiClient(
        "2001:db8::1",
        "camera user",
        "p@ss/word",
        rtsp_port=8554,
    )

    assert client.rtsp_url(channel_id=16, stream="sub") == (
        "rtsp://camera%20user:p%40ss%2Fword@[2001:db8::1]:8554/Streaming/Channels/1602"
    )


def test_rtsp_snapshot_uses_tuned_single_frame_command(monkeypatch):
    calls = []
    image = b"\xff\xd8frame\xff\xd9"

    def fake_run(args, *, capture_output, timeout, check):
        calls.append((args, capture_output, timeout, check))
        return subprocess.CompletedProcess(args, 0, stdout=image, stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = IsapiClient("10.40.31.250", "operator", "secret")

    assert client.snapshot_rtsp(channel_id=6, stream="sub", timeout=3) == image
    args, capture_output, timeout, check = calls[0]
    assert args[0] == "ffmpeg"
    assert "-probesize" in args
    assert "32" in args
    assert args[-2:] == ["image2", "pipe:1"]
    assert "/Streaming/Channels/602" in args[args.index("-i") + 1]
    assert capture_output is True
    assert timeout == 5
    assert check is False


def test_rtsp_snapshot_maps_timeout_without_echoing_url(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 3)

    monkeypatch.setattr(subprocess, "run", timeout)
    client = IsapiClient("10.40.31.250", "operator", "secret")

    with pytest.raises(HikUnreachableError, match="timed out") as exc:
        client.snapshot_rtsp(channel_id=16, timeout=3)

    assert "secret" not in str(exc.value)
