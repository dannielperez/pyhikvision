# Changelog

All notable changes to **pyhikvision** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **Channel enumeration.** `IsapiClient.input_proxy_channels()` (the IP cameras
  an NVR has adopted, `GET /ISAPI/ContentMgmt/InputProxy/channels`),
  `video_input_channels()` (the device's own local inputs,
  `GET /ISAPI/System/Video/inputs/channels`), and `channels()` which merges both
  families and de-duplicates by `(kind, id)`.
- `ChannelInfo` public dataclass — typed row carrying `id`, `name`, `online`,
  `source_ip`, `source_port`, `source_channel`, `protocol`, and `kind`.
- Optional `with_status=True` merges `online` flags from
  `GET /ISAPI/ContentMgmt/InputProxy/channels/status`. Without it `online` stays
  `None` so a caller can tell "offline" from "not asked".
- Every enumeration call accepts an explicit `timeout` that overrides the client
  default for that request only.

  Degradation is deliberate: a device implementing only one channel family is
  fine (the missing family is skipped), a missing/failing status endpoint leaves
  `online` unknown rather than failing enumeration, and rows without a usable
  integer `id` are skipped rather than guessed at. `channels()` raises only when
  BOTH families fail, so a broken device never looks like one with no cameras.
  Parsing is namespace-agnostic (`hikvision.com` and `std-cgi.com` both seen in
  the field).

  Fixtures follow the ISAPI 2.x specification rather than a single captured
  firmware; live validation against a recorder is deliberately out of scope for
  this change.
- Guarded `get_line_detection` and `set_line_detection` ISAPI operations with
  normalized-coordinate validation, XML-preserving updates, no-op suppression,
  and optional read-back verification.
- `LineDetectionConfig` public dataclass.

## [0.1.0] — 2026-04-26

### Added
- Initial release.
- `IsapiClient` — pure-Python Hikvision ISAPI client (HTTP Digest + Basic
  fallback). Endpoints: `deviceInfo`, `Network/interfaces/{n}/ipAddress`
  (GET/PUT), `System/reboot`.
- `HikClient` — high-level facade defaulting to ISAPI.
- `batch_set_ip` — parallel IP-migration helper with serial submit + parallel
  TCP verification (new-up-old-down rule + transitional 30s old-closed
  fallback).
- `pyhik` CLI with `info`, `set-ip`, and `batch` subcommands.
- `netsdk` backend skeleton with availability detection
  (`HIKVISION_SDK_DIR` / `binaries/linux/<arch>/`); methods raise
  `NotImplementedError` until the HCNetSDK bindings are wired up.
- Smoke test suite (`tests/test_smoke.py`).
