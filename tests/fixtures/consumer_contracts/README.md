# Consumer contract replay fixtures

Spec-shaped Hikvision ISAPI response bodies used to pin the wire shapes that
`IsapiClient` parses on behalf of the `hikvision_sdk` boundary
(`uniqueos/devices/services/hikvision_sdk.py`). They contain no credentials,
customer hostnames, or real device identifiers.

- `device_info.xml` — `GET /ISAPI/System/deviceInfo` success body.

Tests replay this file entirely in-process by stubbing `IsapiClient._request`
(or its underlying `requests.Session`); they never contact a device.
