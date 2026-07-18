"""Lightweight dataclasses returned by HikClient."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional


@dataclass
class DeviceInfo:
    device_name: Optional[str] = None
    device_id: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    mac_address: Optional[str] = None
    firmware_version: Optional[str] = None
    firmware_released_date: Optional[str] = None
    device_type: Optional[str] = None
    raw_xml: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw_xml", None)
        return d


@dataclass
class NetworkConfig:
    ip: Optional[str] = None
    mask: Optional[str] = None
    gateway: Optional[str] = None
    dns1: Optional[str] = None
    dns2: Optional[str] = None
    dhcp: Optional[bool] = None
    mac_address: Optional[str] = None
    mtu: Optional[int] = None
    raw_xml: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw_xml", None)
        return d


@dataclass
class LineDetectionConfig:
    """One ISAPI line-crossing rule and its normalized image geometry."""

    channel_id: int
    line_id: int
    enabled: bool
    global_enabled: bool
    item_enabled: bool
    multi_scene_supported: bool
    sensitivity: int
    direction: str
    start: tuple[int, int]
    end: tuple[int, int]
    screen_width: int = 1000
    screen_height: int = 1000
    raw_xml: Optional[str] = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d.pop("raw_xml", None)
        return d
