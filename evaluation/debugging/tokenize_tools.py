#!/usr/bin/env python3
"""Secondary, offline reference counts of all saved solver-visible responses.

These counts do not replace actual CLI usage or estimate API charges. Different
solvers can make different requests; aggregate volumes are not matched-command
compression percentages. This helper does not execute commands or call models.
"""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path


def count_responses(root: Path, cache: Path) -> dict:
    import requests
    import tiktoken
    if importlib.metadata.version("tiktoken") != "0.14.0":
        raise ValueError("use the pinned evaluation requirements: tiktoken 0.14.0")
    os.environ["TIKTOKEN_CACHE_DIR"] = str(cache.resolve(strict=True))
    def blocked(*args, **kwargs):
        raise RuntimeError("tokenizer download is forbidden; provision the cache first")
    previous = requests.get
    try:
        requests.get = blocked
        encoders = {name: tiktoken.get_encoding(name) for name in ("o200k_base", "cl100k_base")}
    finally:
        requests.get = previous
    plan_bytes = (root / "plan.json").read_bytes()
    plan = json.loads(plan_bytes)
    rows = []
    for trial in plan["trials"]:
        log = root / "trials" / trial["id"] / "artifacts/tools.jsonl"
        if not (log.parent.parent / "result.json").exists():
            raise ValueError("all sessions must finish before secondary tokenization")
        records = [json.loads(line) for line in log.read_text().splitlines() if line]
        counts = {name: {"all_responses": 0, "terminal_responses": 0, "read_responses": 0, "recovery_responses": 0, "write_and_list_responses": 0, "request_arguments": 0} for name in encoders}
        for record in records:
            visible = json.dumps(record["visible"], ensure_ascii=False)
            arguments = json.dumps(record["arguments"], ensure_ascii=False)
            category = {"terminal": "terminal_responses", "read_file": "read_responses", "recover_output": "recovery_responses"}.get(record["tool"], "write_and_list_responses")
            for name, encoder in encoders.items():
                number = len(encoder.encode(visible, disallowed_special=()))
                counts[name]["all_responses"] += number
                counts[name][category] += number
                counts[name]["request_arguments"] += len(encoder.encode(arguments, disallowed_special=()))
        rows.append({**trial, "tool_log_sha256": hashlib.sha256(log.read_bytes()).hexdigest(), "actions": len(records), "reference_tokens": counts})
    grouped = {}
    for variant in ("raw", "mini", "rtk"):
        selected = [row for row in rows if row["variant"] == variant]
        grouped[variant] = {name: {key: sum(row["reference_tokens"][name][key] for row in selected) for key in selected[0]["reference_tokens"][name]} for name in encoders}
    return {"schema": 1, "plan_sha256": hashlib.sha256(plan_bytes).hexdigest(), "tiktoken_version": "0.14.0", "encodings": list(encoders), "cache_files_sha256": sorted(hashlib.sha256(path.read_bytes()).hexdigest() for path in cache.iterdir() if path.is_file()), "by_variant": grouped, "trials": rows,
            "definition": "Encode each exact JSON text string delivered as a tool content block; count request arguments separately. Excludes model instructions, reasoning, model messages, protocol wrappers and repeated context. CLI actual whole-session usage is the primary measure. Different request sets mean these volumes are not matched-command compression ratios."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--tokenizer-cache", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = count_responses(args.run_root.resolve(), args.tokenizer_cache.resolve())
    with args.output.open("x") as output:
        json.dump(result, output, indent=2, sort_keys=True)
        output.write("\n")
