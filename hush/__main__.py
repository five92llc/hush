"""Run with:  python -m hush  [--config config.yaml]"""
import argparse
import logging
import os

import uvicorn

from .app import create_app
from .config import load_config


def main() -> None:
    ap = argparse.ArgumentParser(prog="hush", description="Hush media server")
    ap.add_argument("--config", default=os.environ.get("HUSH_CONFIG", "config.yaml"))
    ap.add_argument("--host")
    ap.add_argument("--port", type=int)
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cfg = load_config(args.config)
    if args.host:
        cfg.host = args.host
    if args.port:
        cfg.port = args.port
    uvicorn.run(create_app(cfg), host=cfg.host, port=cfg.port, log_level="info",
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")


if __name__ == "__main__":
    main()
