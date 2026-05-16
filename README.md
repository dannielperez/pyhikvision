# pyhikvision

Unified Python toolkit for Hikvision devices. **Two backends, one API.**

| Backend | Implementation | Where it runs | What it's for |
|---|---|---|---|
| **isapi** | Pure Python (`requests` + HTTP Digest) | Anywhere — macOS, Linux, Windows, **over WireGuard** | IP/network management, device info, reboot, user mgmt, ONVIF-equivalent ops |
| **netsdk** | ctypes bindings to **HCNetSDK** | Linux only (vendor binaries) | SADP discovery, RTSP playback, video search, deeper device queries |

The high-level `HikClient` defaults to **ISAPI** (no native deps). The
`netsdk` backend is opt-in for features ISAPI cannot cover.

This is the merged successor to public projects like `Rennbon/pyhikvision`,
`kamokr/pyhikvision`, and various ISAPI-only clients — forked, cleaned up,
and adapted to mirror the layout of our internal `pytvt` package.

## Quick start (ISAPI — no SDK needed)

```python
from pyhikvision import HikClient

with HikClient("192.168.1.64", "admin", "MyPass!") as cam:
    info = cam.device_info()
    print(info.device_name, info.serial_number, info.firmware_version)

    cam.set_network_config(
        ip="10.0.0.10",
        mask="255.255.255.0",
        gateway="10.0.0.1",
        dns1="8.8.8.8",
    )
    cam.reboot()
```

## Batch IP migration (parallel)

```python
from pyhikvision import batch_set_ip

results = batch_set_ip(
    pairs=[{"old_ip": "192.168.1.64", "new_ip": "10.0.0.10"}, ...],
    user="admin",
    password="MyPass!",
    gateway="10.0.0.1",
    mask="255.255.255.0",
    workers=8,
    verify=True,
)
```

## NetSDK escalation (Linux only)

The `netsdk` backend is shipped without binary blobs. Drop the official
HCNetSDK Linux bundle into `binaries/linux/{x86_64,arm64}/` (or set
`HIKVISION_SDK_DIR`) before importing.

## Architectural notes

- **macOS Rosetta hangs on `NET_DVR_Init`** — same class of issue as TVT's
  `NET_CLIENT_Initial`. Use ISAPI on macOS, or run NetSDK inside a Linux
  Docker container (mirrors our pytvt approach).
- **SADP multicast doesn't traverse WireGuard.** ISAPI is the only path for
  remote-site IP migrations.
