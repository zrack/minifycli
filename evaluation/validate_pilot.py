#!/usr/bin/env python3
"""Independently validate the canonical 16-case, three-repetition v0.2 pilot.

This focused audit reads retained capture bytes and pinned tokenizer data. It
never imports the collector's calculation helpers, reruns workload commands,
or prints captured source text or comprehension answers. It intentionally
requires the registered plan and collector version from the matching checkout.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import statistics
import sys
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
ENCODINGS = ('o200k_base', 'cl100k_base')


def validate(run_root: Path, tokenizer_cache: Path) -> dict:
    if not __debug__:
        raise ValueError('Validation requires assertions; do not use Python -O')
    RUN = run_root.resolve()
    CACHE = tokenizer_cache.resolve()
    results = json.loads((RUN / 'results.json').read_text())
    plan_bytes = (RUN / 'registered-plan.json').read_bytes()
    plan = json.loads(plan_bytes)
    hash_bytes = lambda data: hashlib.sha256(data).hexdigest()
    assert results['finished_utc'] > results['started_utc']
    assert hash_bytes(plan_bytes) == results['plan_sha256']
    assert hash_bytes((PROJECT / 'evaluation/plans/pilot-v0.2.json').read_bytes()) == results['plan_sha256']
    assert hash_bytes((PROJECT / 'evaluation/run_pilot.py').read_bytes()) == results['harness_sha256']
    assert importlib.metadata.version('tiktoken') == results['tokenizer']['version']
    assert list(ENCODINGS) == results['tokenizer']['encodings']
    for name, digest in results['tokenizer']['cache_sha256'].items():
        assert hash_bytes((CACHE / name).read_bytes()) == digest
    os.environ['TIKTOKEN_CACHE_DIR'] = str(CACHE)
    import tiktoken
    with patch('requests.get', side_effect=RuntimeError('Independent validation must remain offline')):
        encoders = {name: tiktoken.get_encoding(name) for name in ENCODINGS}

    case_by_id = {c['id']: c for c in results['cases']}
    assert list(case_by_id) == [c['id'] for c in plan['cases']]
    assert len(case_by_id) == len(plan['cases']) == 16
    assert results['repetitions'] == 3
    plan_by_id = {c['id']: c for c in plan['cases']}
    checked = {}
    fresh_metrics = {}
    contract_count = 0


    def stream(path, reported=None):
        path = path.resolve()
        assert RUN in path.parents
        data = path.read_bytes()
        actual = {'bytes': len(data), 'sha256': hash_bytes(data)}
        try:
            text = data.decode('utf-8', errors='strict')
            actual['utf8'] = True
            actual['tokens'] = {name: len(encoders[name].encode(text, disallowed_special=())) for name in ENCODINGS}
        except UnicodeDecodeError:
            actual['utf8'] = False
            actual['tokens'] = {name: None for name in ENCODINGS}
        if reported is not None:
            assert actual == reported, f'Measure mismatch: {path.relative_to(RUN)}'
        checked[str(path.relative_to(RUN))] = actual
        return data, actual


    def check_contracts(data, definitions):
        nonlocal contract_count
        text = data.decode('utf-8', errors='strict')
        values = [{'id': d['id'], 'passed': any(re.search(pattern, text, re.MULTILINE) is not None for pattern in d['any'])} for d in definitions]
        contract_count += len(values)
        return values


    def trial(row, definitions, expected):
        capture = RUN / row['private_capture']
        stdout, a = stream(capture / 'stdout', row['stdout'])
        stderr, b = stream(capture / 'stderr', row['stderr'])
        assert row['capture_complete'] is True
        assert row['timed_out'] is False and row['output_limit'] is False
        assert row['returncode'] == expected and row['exit_matches_expected'] is True
        checks = check_contracts(stdout + b'\n' + stderr, definitions)
        assert checks == row['contracts'] and all(c['passed'] for c in checks)
        return {e: a['tokens'][e] + b['tokens'][e] for e in ENCODINGS}

    for case in results['cases']:
        definition = plan_by_id[case['id']]
        assert case['argv'] == definition['argv']
        assert case['group'] == definition['group']
        assert case['repo'] == definition['repo']
        assert case['expected_exit'] == definition['expected_exit']
        assert case['rtk_native_argv'] == definition['rtk_native']
        shared = case['same_capture']
        record = RUN / shared['private_record']
        metadata = json.loads((record / 'metadata.json').read_text())
        assert metadata['complete'] is True and not metadata['cancelled']
        assert not metadata['stdout_spilled'] and not metadata['stderr_spilled']
        assert metadata['exit_code'] == definition['expected_exit']
        assert metadata['failed'] == (metadata['exit_code'] != 0)
        assert [bytes.fromhex(x).decode() for x in metadata['argv_hex']] == case['argv']
        assert shared['record_status_matches_expected'] is True and shared['replay_exact'] is True
        assert shared['stderr_included_in_token_comparison'] is False
        raw_out, raw_a = stream(record / 'stdout.raw', shared['raw']['stdout'])
        raw_err, raw_b = stream(record / 'stderr.raw', shared['raw']['stderr'])
        mini_out, mini_a = stream(record / 'stdout.filtered', shared['mini']['stdout'])
        mini_err, mini_b = stream(record / 'stderr.filtered', shared['mini']['stderr'])
        for suffix, payload, length_key in [('stdout.raw', raw_out, 'stdout_raw_bytes'), ('stderr.raw', raw_err, 'stderr_raw_bytes'), ('stdout.filtered', mini_out, 'stdout_filtered_bytes'), ('stderr.filtered', mini_err, 'stderr_filtered_bytes')]:
            assert metadata[length_key] == len(payload)
        directory = RUN / 'captures' / case['id']
        assert (directory / 'record-live/stdout').read_bytes() == mini_out
        assert (directory / 'record-live/stderr').read_bytes() == mini_err
        assert (directory / 'replay/stdout').read_bytes() == mini_out
        assert (directory / 'replay/stderr').read_bytes() == mini_err
        before = check_contracts(raw_out, definition['contracts'])
        after = check_contracts(mini_out, definition['contracts'])
        expected = [{'id': x['id'], 'eligible': x['passed'], 'passed': y['passed'] if x['passed'] else None} for x, y in zip(before, after)]
        assert expected == shared['mini']['contracts_stdout']
        assert all(x['passed'] is not False for x in expected)
        metrics = {'shared': {'raw': raw_a['tokens'], 'mini': mini_a['tokens']}, 'native': {}}
        pipe = shared['rtk_pipe']
        assert (pipe is not None) == (definition['rtk_pipe'] is not None)
        if pipe is not None:
            pipe_out, pipe_a = stream(directory / 'rtk-pipe/stdout', pipe['stdout'])
            pipe_err, pipe_b = stream(directory / 'rtk-pipe/stderr', pipe['stderr'])
            assert pipe['filter_complete'] is True and pipe['filter_returncode'] == 0
            metrics['shared']['rtk_pipe'] = pipe_a['tokens']
            after = check_contracts(pipe_out, definition['contracts'])
            expected = [{'id': x['id'], 'eligible': x['passed'], 'passed': y['passed'] if x['passed'] else None} for x, y in zip(before, after)]
            assert expected == pipe['contracts_stdout']
            assert all(x['passed'] is not False for x in expected)
        expected_variants = {'raw', 'mini'} | ({'rtk'} if definition['rtk_native'] is not None else set())
        assert set(case['native']) == expected_variants
        assert set(case['warmups']) == expected_variants
        for name, warmup in case['warmups'].items():
            trial(warmup, definition['contracts'], definition['expected_exit'])
        for name, rows in case['native'].items():
            assert len(rows) == 3
            metrics['native'][name] = [trial(row, definition['contracts'], definition['expected_exit']) for row in rows]
        for order in case['trial_variant_orders']:
            assert set(order) == expected_variants and len(order) == len(expected_variants)
        if expected_variants == {'raw', 'mini', 'rtk'}:
            assert all(sum(order[0] == v for order in case['trial_variant_orders']) == 1 for v in expected_variants)
        fresh_metrics[case['id']] = metrics

    percent = lambda a,b: None if a == 0 else 100.0 * (a-b) / a
    summary = {}
    for group in ('ordinary', 'controlled'):
        selected = [c for c in results['cases'] if c['group'] == group]
        common_shared = [c for c in selected if 'rtk_pipe' in fresh_metrics[c['id']]['shared']]
        common_native = [c for c in selected if 'rtk' in fresh_metrics[c['id']]['native']]
        shared_output = {}
        native_output = {}
        for e in ENCODINGS:
            raw = sum(fresh_metrics[c['id']]['shared']['raw'][e] for c in common_shared)
            shared_output[e] = {}
            for variant in ('mini', 'rtk_pipe'):
                value = sum(fresh_metrics[c['id']]['shared'][variant][e] for c in common_shared)
                metric = {'cases': len(common_shared), 'raw_tokens': raw, 'output_tokens': value, 'reduction_percent': percent(raw,value)}
                reported = results['summary']['same_capture_common'][group]['variants'][variant]['encodings'][e]
                assert reported['valid_cases'] == len(common_shared) and reported['excluded_cases'] == 0
                assert reported['raw_tokens'] == raw and reported['output_tokens'] == value
                assert reported['reduction_percent'] == metric['reduction_percent']
                shared_output[e][variant] = metric
            native_output[e] = {}
            for variant in ('raw', 'mini', 'rtk'):
                a = sum(fresh_metrics[c['id']]['native']['raw'][i][e] for c in common_native for i in range(3))
                b = sum(fresh_metrics[c['id']]['native'][variant][i][e] for c in common_native for i in range(3))
                metric = {'trials': len(common_native)*3, 'raw_tokens': a, 'output_tokens': b, 'reduction_percent': percent(a,b)}
                reported = results['summary']['native_common'][group]['variants'][variant]['encodings'][e]
                assert reported['paired_trials'] == len(common_native)*3 and reported['excluded_pairs'] == 0
                assert reported['raw_tokens'] == a and reported['output_tokens'] == b
                assert reported['reduction_percent'] == metric['reduction_percent']
                native_output[e][variant] = metric
        summary[group] = {'shared_case_ids': [c['id'] for c in common_shared], 'native_case_ids': [c['id'] for c in common_native], 'shared': shared_output, 'native': native_output}

    ordinary_native = [c for c in results['cases'] if c['group'] == 'ordinary' and 'rtk' in fresh_metrics[c['id']]['native']]
    per_case = []
    for case in ordinary_native:
        values = {v: sum(x['o200k_base'] for x in fresh_metrics[case['id']]['native'][v]) for v in ('raw', 'mini', 'rtk')}
        deltas = {}
        first_deltas = {}
        for variant in ('mini', 'rtk'):
            deltas[variant] = 1000*statistics.median(case['native'][variant][i]['wall_seconds'] - case['native']['raw'][i]['wall_seconds'] for i in range(3))
            available = [(case['native'][variant][i]['time_to_first_output_seconds'], case['native']['raw'][i]['time_to_first_output_seconds']) for i in range(3)]
            first_deltas[variant] = 1000*statistics.median(a-b for a,b in available if a is not None and b is not None) if all(a is not None and b is not None for a,b in available) else None
        per_case.append({'id': case['id'], 'repo': case['repo'], 'tokens_o200k': values, 'saved_o200k': {v: values['raw']-values[v] for v in ('mini','rtk')}, 'median_paired_added_wall_ms': deltas, 'median_paired_added_first_output_ms': first_deltas})
    per_repo = {}
    for repo in ('rust','javascript'):
        rows = [r for r in per_case if r['repo'] == repo]
        values = {v: sum(r['tokens_o200k'][v] for r in rows) for v in ('raw','mini','rtk')}
        per_repo[repo] = {'case_ids':[r['id'] for r in rows], 'trials':len(rows)*3, 'tokens_o200k':values, 'reduction_percent':{v:percent(values['raw'], values[v]) for v in ('mini','rtk')}}
    totals = {v: sum(r['tokens_o200k'][v] for r in per_case) for v in ('raw','mini','rtk')}
    for row in per_case:
        row['share_raw_tokens_percent'] = 100*row['tokens_o200k']['raw']/totals['raw']
        row['share_net_saved_tokens_percent'] = {v:100*row['saved_o200k'][v]/(totals['raw']-totals[v]) for v in ('mini','rtk')}
    empty_cases = []
    for case in results['cases']:
        rows = case['native']['raw']
        if all(row['stdout']['bytes'] + row['stderr']['bytes'] == 0 for row in rows):
            empty_cases.append(case['id'])
    report = {'validation_scope':'independent byte hashes and both tokenizer counts; no workload command rerun', 'streams_verified':len(checked), 'native_trials_verified':sum(len(rows) for c in results['cases'] for rows in c['native'].values()), 'warmup_trials_verified':sum(len(c['warmups']) for c in results['cases']), 'record_and_replay_pairs_verified':len(results['cases']), 'contract_evaluations_recomputed':contract_count, 'summaries':summary, 'per_repo_ordinary_native':per_repo, 'per_case_ordinary_native':per_case, 'zero_output_raw_cases':empty_cases, 'unsupported_native_cases':[c['id'] for c in results['cases'] if 'rtk' not in c['native']], 'no_invalid_utf8':all(s['utf8'] for s in checked.values()), 'all_complete_expected_statuses_and_contracts':True, 'plan_sha256':results['plan_sha256'], 'harness_sha256':results['harness_sha256'], 'tiktoken_version':results['tokenizer']['version']}

    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root', required=True, type=Path,
                        help='completed private canonical pilot directory')
    parser.add_argument('--tokenizer-cache', type=Path,
                        default=PROJECT / '.tools/tokenizer-cache',
                        help='previously warmed pinned encoding cache')
    parser.add_argument('--output', type=Path,
                        help='explicit NEW private JSON file; otherwise print metrics to stdout')
    args = parser.parse_args(argv)
    try:
        report = validate(args.run_root, args.tokenizer_cache)
        payload = json.dumps(report, indent=2) + '\n'
        if args.output is None:
            sys.stdout.write(payload)
        else:
            # Existing files and symlinks are never overwritten. Parent
            # directories must already exist; only this requested file is made.
            descriptor = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, 'w', encoding='utf-8') as output:
                output.write(payload)
        return 0
    except (AssertionError, OSError, ValueError, KeyError, TypeError,
            RuntimeError, ImportError) as error:
        # Do not print potentially private paths or captured values from errors.
        print(f'validation failed ({type(error).__name__}); inspect the local run inputs and pinned versions',
              file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
