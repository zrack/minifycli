#!/usr/bin/env python3
"""Run held-out Rust regressions outside a solver's exported source tree.

Only the subject's normal dependencies are compiled. The subject's upstream
dev-dependencies and its in-tree tests are deliberately not part of this check.
Run the upstream suite separately with the task's baseline_command.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_id", choices=["C-R1", "C-R2", "C-R3"])
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--cargo", default="cargo")
    parser.add_argument("--target-dir", type=Path)
    options = parser.parse_args()
    workspace = options.workspace.resolve(strict=True)
    package = "glob" if options.task_id == "C-R3" else "winnow"
    fixture = Path(__file__).resolve().with_name(options.task_id + "-hidden.rs")
    with tempfile.TemporaryDirectory(prefix="minifycli-held-out-") as folder:
        harness = Path(folder)
        (harness / "tests").mkdir()
        shutil.copyfile(fixture, harness / "tests" / "regression.rs")
        manifest = (
            '[package]\nname = "held-out-regression"\nversion = "0.0.0"\n'
            'edition = "2021"\npublish = false\n\n[dependencies]\n'
            f'subject = {{ package = "{package}", path = {json.dumps(str(workspace))} }}\n'
        )
        (harness / "Cargo.toml").write_text(manifest, encoding="utf-8")
        command = [options.cargo, "test", "--offline", "--manifest-path", str(harness / "Cargo.toml")]
        if options.target_dir:
            command.extend(["--target-dir", str(options.target_dir.resolve())])
        command.extend(["--", "--test-threads=1"])
        return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
