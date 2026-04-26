"""pyhikvision CLI — minimal, focused on IP migration workflows."""

from __future__ import annotations

import argparse
import json
import sys

from . import HikClient, batch_set_ip


def cmd_info(args: argparse.Namespace) -> int:
    with HikClient(
        args.host, args.user, args.password, scheme=args.scheme, timeout=args.timeout
    ) as cam:
        info = cam.device_info()
        net = cam.get_network_config()
        print(json.dumps({"device": info.to_dict(), "network": net.to_dict()}, indent=2))
    return 0


def cmd_set_ip(args: argparse.Namespace) -> int:
    with HikClient(
        args.host, args.user, args.password, scheme=args.scheme, timeout=args.timeout
    ) as cam:
        cam.set_network_config(
            ip=args.ip,
            mask=args.mask,
            gateway=args.gateway,
            dns1=args.dns1,
            dns2=args.dns2,
        )
        if not args.no_reboot:
            cam.reboot()
    print(json.dumps({"ok": True, "host": args.host, "new_ip": args.ip}))
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    pairs = []
    for spec in args.pair:
        old_ip, new_ip = spec.split(":", 1)
        pairs.append({"old_ip": old_ip, "new_ip": new_ip})
    results = batch_set_ip(
        pairs=pairs,
        user=args.user,
        password=args.password,
        gateway=args.gateway,
        mask=args.mask,
        dns1=args.dns1,
        dns2=args.dns2,
        scheme=args.scheme,
        workers=args.workers,
        verify=not args.no_verify,
        verify_deadline=args.deadline,
    )
    print(json.dumps(results, indent=2))
    return 0 if all(r["status"] in ("OK", "SKIP_UNREACHABLE") for r in results) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser("pyhik")
    p.add_argument("-u", "--user", required=True)
    p.add_argument("-p", "--password", required=True)
    p.add_argument("--scheme", default="http", choices=["http", "https"])
    p.add_argument("--timeout", type=float, default=10.0)
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("info", help="Print deviceInfo + network config as JSON")
    pi.add_argument("host")
    pi.set_defaults(func=cmd_info)

    ps = sub.add_parser("set-ip", help="Change a single device's IP and reboot")
    ps.add_argument("host")
    ps.add_argument("--ip", required=True)
    ps.add_argument("--mask", required=True)
    ps.add_argument("--gateway", required=True)
    ps.add_argument("--dns1")
    ps.add_argument("--dns2")
    ps.add_argument("--no-reboot", action="store_true")
    ps.set_defaults(func=cmd_set_ip)

    pb = sub.add_parser("batch", help="Re-IP many devices in parallel")
    pb.add_argument("--mask", required=True)
    pb.add_argument("--gateway", required=True)
    pb.add_argument("--dns1")
    pb.add_argument("--dns2")
    pb.add_argument(
        "--pair",
        action="append",
        required=True,
        help="old_ip:new_ip (repeatable)",
    )
    pb.add_argument("--workers", type=int, default=8)
    pb.add_argument("--deadline", type=float, default=90.0)
    pb.add_argument("--no-verify", action="store_true")
    pb.set_defaults(func=cmd_batch)

    return p


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
