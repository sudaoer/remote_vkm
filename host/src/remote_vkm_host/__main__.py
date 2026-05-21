from __future__ import annotations

import argparse
import logging
import sys

from .client import RemoteVkmClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Forward local keyboard and mouse events to a remote-vkm receiver.")
    parser.add_argument("--host", required=True, help="receiver host name or IP address")
    parser.add_argument("--port", type=int, default=5533, help="receiver TCP port")
    parser.add_argument(
        "--capture",
        choices=["window", "global"],
        default="window",
        help="capture mode: window opens a VM-style grab window; global uses the legacy global hooks",
    )
    parser.add_argument("--verbose", action="store_true", help="enable debug logging")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        with RemoteVkmClient(args.host, args.port) as client:
            if args.capture == "global":
                from .capture import InputForwarder

                InputForwarder(client).run()
            else:
                from .window_capture import WindowForwarder

                WindowForwarder(client).run()
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
