#!/usr/bin/env python3
"""Use the frozen terminal boundary with a common confirmation wrap-up deadline."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time


DEBUGGING = Path(__file__).resolve().parents[1] / "debugging"
sys.path.insert(0, str(DEBUGGING))
# Load under an explicit module name to avoid importing this entry point again.
import importlib.util
spec = importlib.util.spec_from_file_location("frozen_debugging_mcp", DEBUGGING / "mcp_server.py")
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
from terminal import TerminalSession


class ConfirmationServer(base.Server):
    def __init__(self, config):
        super().__init__(config)
        self.session = TerminalSession(self.root, self.artifacts / "commands", config["mode"], Path(config["mini"]), Path(config["rtk"]), env=config.get("env"))
        unset = config.get("environment_unset", [])
        if not isinstance(unset, list) or any(key not in {"NO_COLOR", "FORCE_COLOR"} for key in unset):
            raise ValueError("only registered color-environment unsets are allowed")
        for key in unset:
            self.session.env.pop(key, None)
        with (self.artifacts / "command-environment.json").open("x") as output:
            json.dump({"declared_unset": unset, "effective_keys": sorted(self.session.env), "values_recorded": False}, output)

    def call(self, name, args):
        if time.time() >= self.config["soft_deadline_epoch"]:
            self.calls += 1
            return {"error": "The common workspace-action deadline has passed. No further workspace actions are accepted. Do not request more tools; finish with your current patch and report verification completed so far."}
        return super().call(name, args)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    def terminated(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminated)
    server = ConfirmationServer(json.loads(args.config.read_text()))
    for line in sys.stdin:
        response = server.handle(json.loads(line))
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
