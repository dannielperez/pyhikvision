# Handoff — codex/access-control-media

HANDOFF: `codex/access-control-media` · 2026-07-30
- objective: expose exact Hikvision recorder-channel still-image routes for Access Control
- state: implemented; draft PR pending
- changed: `HikClient`/`IsapiClient` now map one-based inputs to ISAPI/RTSP channel IDs, fetch native JPEGs, and support bounded tuned RTSP frame grabs
- validations: `pytest -q` OK 90 passed; changed-file `ruff check` and `ruff format --check` OK
- baseline: repository-wide ruff still reports the pre-existing unused `Iterable` import in `isapi/batch.py` and pre-existing formatting drift in three unrelated files
- safety: no device call, secret, deployment, release, or merge; RTSP errors never render the credential-bearing URL
- next: merge the SDK PR, pin its exact commit in UniqueOS, add the provider-dispatching media adapter, and live-probe Estancias channels 6 and 16 in UAT
