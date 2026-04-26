# Changelog

All notable changes to **pyhikvision** will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/).

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
