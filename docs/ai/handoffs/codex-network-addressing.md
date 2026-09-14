HANDOFF: codex/network-addressing · 2026-09-14 UTC
- objective: make ISAPI IPv4 updates safe for DHCP-only, static and DNS changes.
- changed: `src/pyhikvision/isapi/client.py` patches only requested fields, selects the direct device IP rather than nested gateway IP, retains namespace/extensions, requires a valid successful ResponseStatus and never replays ambiguous writes.
- tests: `tests/test_network_configuration.py` adds 13 network regressions. `PYTHONPATH=src python -m pytest -q`: 111 passed. The new gateway-first regression fails on the original pinned source (`1cf0771`).
- lint: standalone `ruff check --isolated src/pyhikvision/isapi/client.py tests/test_network_configuration.py` passes. The parent application's lint policy is not this standalone SDK's policy; no mass reformat/lint-policy migration performed.
- risk: existing callers now receive an error for missing/invalid/negative ResponseStatus even after HTTP 2xx; the device may already have changed IP, so callers must reconcile rather than repeat. DHCP/static firmware lab verification remains outstanding.
- reviews: stability-reviewer OK; sdk-boundary-reviewer OK; no schema changes.
- safety: synthetic fixtures and mocked transport only; no device calls, secrets, migration or deployment.
- next: review SDK change, run firmware-specific lab verification, then update consuming gitlinks when the SDK revision is accepted.
