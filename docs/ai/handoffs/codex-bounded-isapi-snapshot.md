# Bounded native ISAPI snapshot

- branch: `codex/bounded-isapi-snapshot`
- outcome: native JPEG responses stream in 64 KiB chunks, stop above 8 MiB,
  divide the aggregate budget across fixed authentication/header/body phases,
  recompute remaining time before Basic fallback, enforce the caller's monotonic
  content deadline, and close responses on every exit
- auth/error handling: Basic fallback closes the prior Digest response; streamed
  non-success bodies are not buffered into exception details
- validation: `98 passed`; scoped fatal/static checks and `git diff --check` pass
- live vendor calls: not run
- consumer: UniqueOS Access Control explicit Hikvision Main/Sub native still routing
- rollback: revert the commit; no device mutation or persistent-data change
