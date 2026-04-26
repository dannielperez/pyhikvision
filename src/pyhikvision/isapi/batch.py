"""Parallel batch IP-change helper.

Mirrors the pattern used by the TVT SDK daemon:
- Phase 1: serial submit (login -> set -> reboot) to avoid hammering one
  device with overlapping config writes.
- Phase 2: parallel verification (TCP probe) of new vs old IP.

A camera is considered migrated when *either*:
- new_ip:80 is open (camera is back up on its new address), OR
- old_ip:80 has been closed continuously for >= ``transitional_window`` seconds
  (camera has stopped answering on the old IP, taken as definitive proof of
  the change while the new IP is still booting).
"""

from __future__ import annotations

import concurrent.futures as cf
import logging
import socket
import time
from typing import Iterable, List, Optional, Sequence

from .client import IsapiClient
from ..exceptions import HikError, HikUnreachableError

logger = logging.getLogger(__name__)


def _tcp_open(ip: str, port: int = 80, timeout: float = 2.0) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((ip, port))
        s.close()
        return True
    except Exception:
        return False


def _verify_one(
    *,
    old_ip: str,
    new_ip: str,
    deadline: float,
    transitional_window: float = 30.0,
    poll_interval: float = 3.0,
    port: int = 80,
) -> dict:
    old_closed_since: Optional[float] = None
    while time.time() < deadline:
        if _tcp_open(new_ip, port=port):
            return {"ok": True, "rule": "new_open"}
        old_open = _tcp_open(old_ip, port=port)
        now = time.time()
        if old_open:
            old_closed_since = None
        else:
            old_closed_since = old_closed_since or now
            if now - old_closed_since >= transitional_window:
                return {"ok": True, "rule": "old_closed_window"}
        time.sleep(poll_interval)
    return {"ok": False, "rule": "deadline"}


def batch_set_ip(
    pairs: Sequence[dict],
    *,
    user: str,
    password: str,
    gateway: str,
    mask: str,
    dns1: Optional[str] = None,
    dns2: Optional[str] = None,
    interface_id: int = 1,
    scheme: str = "http",
    workers: int = 8,
    verify: bool = True,
    verify_deadline: float = 90.0,
    request_timeout: float = 10.0,
) -> List[dict]:
    """Re-IP a batch of Hikvision devices.

    pairs: iterable of dicts with keys ``old_ip``, ``new_ip``.
    Returns list of dicts with ``old_ip``, ``new_ip``, ``submit_ok``,
    ``verify_ok``, ``status``, ``error``.
    """
    results: List[dict] = []

    # Phase 1: serial submit
    for pair in pairs:
        old_ip = pair["old_ip"]
        new_ip = pair["new_ip"]
        entry = {
            "old_ip": old_ip,
            "new_ip": new_ip,
            "submit_ok": False,
            "verify_ok": None,
            "status": "PENDING",
            "error": None,
        }
        if not _tcp_open(old_ip, port=80 if scheme == "http" else 443):
            entry["status"] = "SKIP_UNREACHABLE"
            results.append(entry)
            continue
        try:
            with IsapiClient(
                old_ip,
                user,
                password,
                scheme=scheme,
                interface_id=interface_id,
                timeout=request_timeout,
            ) as cam:
                cam.set_network_config(
                    ip=new_ip,
                    mask=mask,
                    gateway=gateway,
                    dns1=dns1,
                    dns2=dns2,
                )
                cam.reboot()
            entry["submit_ok"] = True
            entry["status"] = "SUBMITTED"
        except HikUnreachableError as exc:
            entry["status"] = "SKIP_UNREACHABLE"
            entry["error"] = str(exc)
        except HikError as exc:
            entry["status"] = "FAIL_SUBMIT"
            entry["error"] = str(exc)
        except Exception as exc:  # noqa: BLE001 - defensive batch wrapper
            entry["status"] = "FAIL_SUBMIT"
            entry["error"] = f"{type(exc).__name__}: {exc}"
        results.append(entry)

    if not verify:
        return results

    # Phase 2: parallel verify
    submitted = [r for r in results if r["submit_ok"]]
    if not submitted:
        return results

    deadline = time.time() + verify_deadline
    port = 80 if scheme == "http" else 443
    with cf.ThreadPoolExecutor(max_workers=min(workers, len(submitted))) as pool:
        futs = {
            pool.submit(
                _verify_one,
                old_ip=r["old_ip"],
                new_ip=r["new_ip"],
                deadline=deadline,
                port=port,
            ): r
            for r in submitted
        }
        for fut in cf.as_completed(futs):
            r = futs[fut]
            try:
                v = fut.result()
            except Exception as exc:  # noqa: BLE001
                r["verify_ok"] = False
                r["status"] = "FAIL_VERIFY"
                r["error"] = f"{type(exc).__name__}: {exc}"
                continue
            r["verify_ok"] = v["ok"]
            r["status"] = "OK" if v["ok"] else "FAIL_VERIFY"
            r["verify_rule"] = v["rule"]
    return results
