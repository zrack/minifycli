#!/usr/bin/env python3
"""Small, auditable stdio MCP adapter for the debugging sprint.

It exposes bounded workspace I/O instead of giving the solver unrestricted
terminal access. Every returned tool response is retained by the collector.
No model credentials are handled by this program.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import signal
import sys
import time


TOOLS = [
    {"name": "terminal", "description": "Run one argv command in the task workspace. No shell syntax. Use this for tests, rg searches, and git diff. Output may be filtered; use recover_output if details are missing.", "inputSchema": {"type": "object", "properties": {"argv": {"type": "array", "items": {"type": "string"}, "minItems": 1}, "cwd": {"type": "string"}, "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 90}}, "required": ["argv"], "additionalProperties": False}},
    {"name": "read_file", "description": "Read a UTF-8 source file within the task workspace. Lines are one-based. Read only the ranges you need.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "from_line": {"type": "integer", "minimum": 1}, "lines": {"type": "integer", "minimum": 1, "maximum": 400}}, "required": ["path"], "additionalProperties": False}},
    {"name": "write_file", "description": "Create or replace a UTF-8 file within the task workspace. Preserve existing source and tests unless the bug requires a change.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"], "additionalProperties": False}},
    {"name": "replace_text", "description": "Replace exactly one occurrence of old text in a workspace file. Include enough unchanged surrounding text to make the match unique.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}, "required": ["path", "old", "new"], "additionalProperties": False}},
    {"name": "list_files", "description": "List files under a relative workspace directory. Excludes Git internals, installed dependencies, and build output.", "inputSchema": {"type": "object", "properties": {"path": {"type": "string"}}, "additionalProperties": False}},
    {"name": "recover_output", "description": "Retrieve a previous command's saved output by artifact_id and stream. source=original requests underlying streams if captured. Where output offers native recall hashes, recall_hash retrieves that stored content; full=true retrieves all stored content. list=true lists native recall entries. All retrieved content counts toward task usage.", "inputSchema": {"type": "object", "properties": {"artifact_id": {"type": "string"}, "stream": {"type": "string", "enum": ["stdout", "stderr"]}, "source": {"type": "string", "enum": ["displayed", "original"]}, "from_line": {"type": "integer", "minimum": 1}, "lines": {"type": "integer", "minimum": 1, "maximum": 400}, "recall_hash": {"type": "string"}, "full": {"type": "boolean"}, "list": {"type": "boolean"}, "grep": {"type": "string"}}, "additionalProperties": False}},
]


def bounded_path(root: Path, name: str) -> Path:
    candidate = (root / name).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("path escapes the workspace")
    if ".git" in candidate.relative_to(root).parts:
        raise ValueError("Git internals are not accessible")
    return candidate


class Server:
    def __init__(self, config: dict):
        self.config = config
        self.root = Path(config["workspace"]).resolve()
        self.artifacts = Path(config["artifact_root"]).resolve()
        self.artifacts.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.calls = 0
        self.started = time.monotonic()
        self.session = None

    def call(self, name: str, args: dict) -> dict:
        self.calls += 1
        if self.calls > self.config.get("max_actions", 60):
            return {"error": "Task action budget exhausted. Finish with your current patch."}
        if name == "list_files":
            path = bounded_path(self.root, args.get("path", "."))
            excluded = {".git", "node_modules", "target", ".cache", "__pycache__"}
            found = []
            for directory, dirs, files in os.walk(path):
                dirs[:] = sorted(d for d in dirs if d not in excluded and not (Path(directory) / d).is_symlink())
                found.extend(str((Path(directory) / file).relative_to(self.root)) for file in sorted(files))
            return {"files": found, "count": len(found)}
        if name == "write_file":
            path = bounded_path(self.root, args["path"])
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(args["content"], encoding="utf-8")
            return {"written": str(path.relative_to(self.root)), "bytes": len(args["content"].encode())}
        if name == "replace_text":
            path = bounded_path(self.root, args["path"])
            text = path.read_text(encoding="utf-8")
            old = args["old"]
            if not old or text.count(old) != 1:
                raise ValueError("old text must match exactly once")
            path.write_text(text.replace(old, args["new"], 1), encoding="utf-8")
            return {"updated": str(path.relative_to(self.root))}
        if self.config.get("smoke"):
            return {"stdout": "sprint smoke ready\n", "stderr": "", "exit_code": 0}
        if self.session is None:
            from terminal import TerminalSession
            self.session = TerminalSession(self.root, self.artifacts / "commands", self.config["mode"], Path(self.config["mini"]), Path(self.config["rtk"]), env=self.config.get("env"))
        actions = {"terminal": "run", "read_file": "read", "recover_output": "recover"}
        if name not in actions:
            raise ValueError("unknown tool")
        if name == "read_file":
            bounded_path(self.root, args["path"])
            args = {"lines": 200, **args}
        return self.session.dispatch({"action": actions[name], **args})

    @staticmethod
    def visible(response: dict) -> dict:
        """Keep bookkeeping out of solver context, retaining it in private logs."""
        if response.get("ok") is False:
            return {"error": response["error"]}
        if "schema_version" not in response:
            return response
        result = {}
        for key in ("artifact_id", "path", "from_line", "total_lines", "capture_complete", "timed_out", "output_limit", "source", "stream", "output_scope", "spawn_error"):
            if key in response and response[key] is not None:
                result[key] = response[key]
        if "returncode" in response:
            result["exit_code"] = response["returncode"]
        for key in ("stdout", "stderr", "content"):
            if key in response:
                stream = response[key]
                result[key] = stream.get("text") if stream.get("encoding") == "utf-8" else {"encoding": "base64", "data": stream.get("base64")}
        if "rtk_recall_hashes" in response and response["rtk_recall_hashes"]:
            result["recall_hashes"] = response["rtk_recall_hashes"]
        if "artifact_id" in response and "argv" in response:
            result["recovery"] = "Use recover_output with this artifact_id and stream. source=original requests child streams where captured; native recall_hash retrieves stored content where available."
        return result

    def handle(self, request: dict) -> dict | None:
        method = request.get("method")
        if "id" not in request:
            return None
        result = {}
        if method == "initialize":
            result = {"protocolVersion": request.get("params", {}).get("protocolVersion", "2024-11-05"), "capabilities": {"tools": {}}, "serverInfo": {"name": "debugging-sprint", "version": "1"}}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request["params"]
            start = time.monotonic()
            try:
                response = self.call(params["name"], params.get("arguments", {}))
            except Exception as exc:
                response = {"error": f"{type(exc).__name__}: {exc}"}
            # Keep original tool result bytes before any client-side presentation.
            visible = self.visible(response)
            entry = {"index": self.calls, "tool": params["name"], "arguments": params.get("arguments", {}), "response": response, "visible": visible, "wall_seconds": time.monotonic() - start}
            with (self.artifacts / "tools.jsonl").open("a", encoding="utf-8") as output:
                output.write(json.dumps(entry, ensure_ascii=False) + "\n")
            result = {"content": [{"type": "text", "text": json.dumps(visible, ensure_ascii=False)}], "isError": "error" in visible}
        elif method == "ping":
            result = {}
        else:
            return {"jsonrpc": "2.0", "id": request["id"], "error": {"code": -32601, "message": "Method not found"}}
        return {"jsonrpc": "2.0", "id": request["id"], "result": result}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    options = parser.parse_args()
    os.umask(0o077)
    def terminated(signum, frame):
        raise SystemExit(128 + signum)
    signal.signal(signal.SIGTERM, terminated)
    server = Server(json.loads(options.config.read_text()))
    for line in sys.stdin:
        request = json.loads(line)
        result = server.handle(request)
        if result is not None:
            print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
