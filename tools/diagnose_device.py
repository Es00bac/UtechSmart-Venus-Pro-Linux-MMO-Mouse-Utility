#!/usr/bin/env python3
"""List supported Venus configuration interfaces and optionally read battery status."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

for parent in Path(__file__).resolve().parents:
    if (parent / "venus_protocol.py").is_file():
        sys.path.insert(0, str(parent))
        break

import venus_protocol as vp


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--battery",
        action="store_true",
        help="send the read-only Areson status command (0x04)",
    )
    args = parser.parse_args()

    if not vp.HIDAPI_AVAILABLE:
        print("python-hidapi is not installed", file=sys.stderr)
        return 2

    devices = vp.list_devices()
    if not devices:
        print("No supported vendor configuration interface found.")
        return 1

    failed = False
    for info in devices:
        print(
            f"{info.vendor_id:04x}:{info.product_id:04x} "
            f"interface={info.interface_number} usage={info.usage_page:04x}:{info.usage:04x} "
            f"path={info.display_path} product={info.product!r}"
        )
        if info.access_error:
            print(f"  access: {info.access_error}")
            failed = True
            continue
        print("  access: OK")

        if args.battery and info.vendor_id == 0x25A7:
            device = vp.VenusDevice(info.path)
            try:
                device.open()
                status = device.query_status()
                connection = "USB cable" if status.cable_connected else "wireless"
                print(
                    f"  battery: {status.percent}% ({connection}, raw={status.raw.hex()})"
                )
            except Exception as exc:
                print(f"  battery read failed: {exc}")
                failed = True
            finally:
                device.close()

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
