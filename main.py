from __future__ import annotations

import argparse
from dataclasses import replace

from cluster_hmi.config import AppConfig
from cluster_hmi.services import build_services
from cluster_hmi.store import ClusterStore
from cluster_hmi.ui.app import ClusterDashboardApp


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Raspberry Pi car cluster HMI trial app")
    parser.add_argument("--demo", action="store_true", help="Run with animated sample data")
    parser.add_argument("--fullscreen", action="store_true", help="Launch in fullscreen mode")
    parser.add_argument("--width", type=int, default=None, help="Window width for desktop preview")
    parser.add_argument("--height", type=int, default=None, help="Window height for desktop preview")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    config = AppConfig.from_env()

    if args.demo:
        config = replace(config, demo_mode=True)
    if args.fullscreen:
        config = replace(config, fullscreen=True)
    if args.width:
        config = replace(config, width=args.width)
    if args.height:
        config = replace(config, height=args.height)

    section_stale_after_s: dict[str, float] = {}
    if config.battery_protocol == "neuwat":
        neuwat_stale_after_s = config.neuwat_section_stale_after_s()
        section_stale_after_s["battery"] = neuwat_stale_after_s
        section_stale_after_s["faults"] = neuwat_stale_after_s

    store = ClusterStore(
        stale_after_s=config.stale_after_s,
        section_stale_after_s=section_stale_after_s,
    )
    services = build_services(config=config, store=store)

    for service in services:
        service.start()

    try:
        app = ClusterDashboardApp(config=config, store=store)
        app.mainloop()
    finally:
        for service in services:
            service.stop()
        for service in services:
            service.join(timeout=1.0)


if __name__ == "__main__":
    main()
