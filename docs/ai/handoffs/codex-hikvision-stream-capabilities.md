# Handoff — codex/hikvision-stream-capabilities

HANDOFF: `codex/hikvision-stream-capabilities` · 2026-07-30
- objective: select a real Hikvision RTSP stream for mixed recorder inputs instead of assuming every input exposes a substream
- state: implemented and locally validated; live validation and draft PR pending
- evidence: Estancias ISAPI advertises enabled `601`, `602`, and `1601`; it does not advertise `1602`. Plain RTSP produced JPEGs from `602` and `1601`, while the previously tuned command failed or timed out.
- changed: added enabled streaming-channel discovery; added bounded `stream="auto"` sub-then-main selection; removed probe flags proven incompatible with the live recorder
- validations: `PYTHONPATH=src pytest -q` OK 95 passed; changed-file Ruff check and format check OK
- baseline: repository-wide Ruff retains unrelated pre-existing lint/format drift
- safety: discovery and ffmpeg share one caller timeout; credential-bearing URLs are not included in exceptions or output
- next: live-run this exact branch against Estancias, open a draft PR, then update UniqueOS to pin the merged SDK commit and request `stream="auto"` for compatibility capture
