"""Hikvision recorder JPEG and RTSP channel mapping, without device I/O."""

from __future__ import annotations

import subprocess
import time

import pytest

from pyhikvision.exceptions import HikError, HikUnreachableError
from pyhikvision.isapi.client import IsapiClient


class _Response:
    def __init__(self, content: bytes = b"", text: str = "") -> None:
        self.content = content
        self.text = text
        self.closed = False

    def iter_content(self, *, chunk_size):
        yield from (
            self.content[offset : offset + chunk_size]
            for offset in range(0, len(self.content), chunk_size)
        )

    def close(self):
        self.closed = True


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

    def fake_request(
        self,
        method,
        path,
        *,
        data=None,
        timeout=None,
        stream=False,
        deadline=None,
    ):
        calls.append((method, path, data, timeout, stream, deadline))
        return _Response(image)

    monkeypatch.setattr(IsapiClient, "_request", fake_request)
    client = IsapiClient("10.40.31.250", "operator", "secret")

    assert client.snapshot(channel_id=16, stream="sub", timeout=4.5) == image
    assert len(calls) == 1
    method, path, data, timeout, streamed, deadline = calls[0]
    assert (method, path, data) == (
        "GET",
        "/ISAPI/Streaming/channels/1602/picture",
        None,
    )
    assert timeout == pytest.approx(4.5 / 8)
    assert streamed is True
    assert deadline is not None


def test_request_basic_fallback_uses_remaining_aggregate_deadline(monkeypatch):
    class AuthResponse:
        def __init__(self, status_code):
            self.status_code = status_code
            self.text = ""
            self.closed = False

        def close(self):
            self.closed = True

    responses = [AuthResponse(401), AuthResponse(200)]
    timeouts = []

    def request(*args, **kwargs):
        timeouts.append(kwargs["timeout"])
        return responses.pop(0)

    clock = iter([10.0, 10.8])
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    client = IsapiClient("10.40.31.250", "operator", "secret")
    monkeypatch.setattr(client._session, "request", request)  # noqa: SLF001

    client._request(  # noqa: SLF001
        "GET",
        "/ISAPI/Streaming/channels/601/picture",
        timeout=1.0,
        deadline=11.0,
        stream=True,
    )

    assert timeouts[0] == 1.0
    assert timeouts[1] == pytest.approx(0.2)


def test_snapshot_refuses_an_empty_response(monkeypatch):
    monkeypatch.setattr(
        IsapiClient,
        "_request",
        lambda *args, **kwargs: _Response(b""),
    )
    client = IsapiClient("10.40.31.250", "operator", "secret")

    with pytest.raises(HikError, match="returned no JPEG image"):
        client.snapshot(channel_id=6)


def test_snapshot_refuses_a_non_jpeg_success_response(monkeypatch):
    monkeypatch.setattr(
        IsapiClient,
        "_request",
        lambda *args, **kwargs: _Response(b"<ResponseStatus>error</ResponseStatus>"),
    )
    client = IsapiClient("10.40.31.250", "operator", "secret")

    with pytest.raises(HikError, match="returned no JPEG image"):
        client.snapshot(channel_id=6)


def test_snapshot_rejects_oversized_main_image_before_buffering(monkeypatch):
    response = _Response()
    response.iter_content = lambda **kwargs: iter(
        [b"\xff\xd8" + (b"x" * (8 * 1024 * 1024))],
    )
    monkeypatch.setattr(
        IsapiClient,
        "_request",
        lambda *args, **kwargs: response,
    )
    client = IsapiClient("10.40.31.250", "operator", "secret")

    with pytest.raises(HikError, match="exceeded maximum image size"):
        client.snapshot(channel_id=6, stream="main")

    assert response.closed is True


def test_snapshot_stops_a_drip_fed_body_at_total_deadline(monkeypatch):
    response = _Response()
    clock = iter([10.0, 10.1, 10.5, 11.1])
    response.iter_content = lambda **kwargs: iter([b"\xff\xd8", b"jpeg", b"\xff\xd9"])
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    monkeypatch.setattr(
        IsapiClient,
        "_request",
        lambda *args, **kwargs: response,
    )
    client = IsapiClient("10.40.31.250", "operator", "secret")

    with pytest.raises(HikUnreachableError, match="snapshot timed out"):
        client.snapshot(channel_id=6, stream="main", timeout=1.0)

    assert response.closed is True


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


def test_rtsp_snapshot_uses_bounded_single_frame_command(monkeypatch):
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
    assert "-probesize" not in args
    assert "-analyzeduration" not in args
    assert "-fflags" not in args
    assert args[-2:] == ["image2", "pipe:1"]
    assert "/Streaming/Channels/602" in args[args.index("-i") + 1]
    assert capture_output is True
    assert 0 < timeout <= 3
    assert check is False


def test_streaming_channel_ids_returns_only_enabled_advertised_streams(monkeypatch):
    xml = """\
    <StreamingChannelList>
      <StreamingChannel><id>602</id><enabled>true</enabled></StreamingChannel>
      <StreamingChannel><id>1601</id><enabled>true</enabled></StreamingChannel>
      <StreamingChannel><id>1602</id><enabled>false</enabled></StreamingChannel>
      <StreamingChannel><id>bad</id><enabled>true</enabled></StreamingChannel>
    </StreamingChannelList>
    """
    calls = []

    def fake_request(self, method, path, *, data=None, timeout=None):
        calls.append((method, path, data, timeout))
        return _Response(text=xml)

    monkeypatch.setattr(IsapiClient, "_request", fake_request)
    client = IsapiClient("10.40.31.250", "operator", "secret")

    assert client.streaming_channel_ids(timeout=2.5) == [602, 1601]
    assert calls == [
        ("GET", "/ISAPI/Streaming/channels", None, 2.5),
    ]


@pytest.mark.parametrize(
    ("advertised", "expected_id"),
    [
        ((601, 602), 602),
        ((1601,), 1601),
    ],
)
def test_rtsp_snapshot_auto_uses_advertised_sub_then_main(
    monkeypatch,
    advertised,
    expected_id,
):
    image = b"\xff\xd8frame\xff\xd9"
    calls = []

    monkeypatch.setattr(
        IsapiClient,
        "streaming_channel_ids",
        lambda self, **kwargs: list(advertised),
    )

    def fake_run(args, *, capture_output, timeout, check):
        calls.append((args, capture_output, timeout, check))
        return subprocess.CompletedProcess(args, 0, stdout=image, stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    client = IsapiClient("10.40.31.250", "operator", "secret")
    channel_id = expected_id // 100

    assert (
        client.snapshot_rtsp(
            channel_id=channel_id,
            stream="auto",
            timeout=3,
        )
        == image
    )
    args, _, subprocess_timeout, _ = calls[0]
    assert f"/Streaming/Channels/{expected_id}" in args[args.index("-i") + 1]
    assert 0 < subprocess_timeout <= 3


def test_rtsp_snapshot_auto_refuses_unadvertised_channel(monkeypatch):
    monkeypatch.setattr(
        IsapiClient,
        "streaming_channel_ids",
        lambda self, **kwargs: [601, 602],
    )
    client = IsapiClient("10.40.31.250", "operator", "secret")

    with pytest.raises(HikError, match="advertises no enabled RTSP stream"):
        client.snapshot_rtsp(channel_id=16, stream="auto", timeout=3)


def test_rtsp_snapshot_maps_timeout_without_echoing_url(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("ffmpeg", 3)

    monkeypatch.setattr(subprocess, "run", timeout)
    client = IsapiClient("10.40.31.250", "operator", "secret")

    with pytest.raises(HikUnreachableError, match="timed out") as exc:
        client.snapshot_rtsp(channel_id=16, timeout=3)

    assert "secret" not in str(exc.value)
