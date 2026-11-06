#!/usr/bin/env python3
"""Post-collection independent audit of the canonical 36-session debugging sprint.

Does not import collector, analyzer, terminal, or evaluator modules. Reads only
frozen artifacts; emits numbers, hashes, IDs, coverage, and audit failures.
Never emits source, model answers, prompts, command output, or private paths.

Written after collection to independently recompute registered outcomes. This
checker was not part of the pre-registered harness and does not alter any trial,
rerun a solver, regrade a repair, or import the original calculation helpers.
It is deliberately specific to the six-task, two-repetition canonical sprint.
Use the original private capture tree and matching evaluator checkout. Local
version checks and Git diff are read-only; no model or network calls are made.
"""
from __future__ import annotations
import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess

REGISTERED='4878a80b6b723648c76312ab5b09d61e72ab9ed2c60d8dc0077a1e24af2ac44b'
ARMS=['raw','mini','rtk']
TASKS=['R1','R2','R3','J1','J2','J3']
EXCLUDE={'.git','target','node_modules','__pycache__','.targetbaseline','.targethidden'}
failures=[]
counts=Counter()

def require(condition,label):
    counts['assertions']+=1
    if not condition: failures.append(label)

def h(data): return hashlib.sha256(data).hexdigest()
def read(path): return json.loads(path.read_bytes())
def digest(path): return h(path.read_bytes())
def jhash(obj,ascii=True): return h(json.dumps(obj,sort_keys=True,ensure_ascii=ascii).encode())
def manifest(root):
    return {p.relative_to(root).as_posix():digest(p) for p in sorted(root.rglob('*')) if p.is_file() and not EXCLUDE.intersection(p.relative_to(root).parts)}
def input_tree_hash(root):
    entries=[{'path':name,'sha256':value,'bytes':(root/name).stat().st_size} for name,value in sorted(manifest(root).items())]
    return h(json.dumps(entries,sort_keys=True,separators=(',',':')).encode())
def dependencies(root):
    deps=root/'node_modules'
    entries={}
    if deps.exists():
        for p in sorted(deps.rglob('*')):
            if '.cache' in p.relative_to(deps).parts: continue
            if p.is_symlink(): entries[p.relative_to(deps).as_posix()]='symlink:'+os.readlink(p)
            elif p.is_file(): entries[p.relative_to(deps).as_posix()]=digest(p)
    return jhash(entries)
def jsonlines(path):
    parsed=[]; malformed=0
    for line in path.read_bytes().splitlines():
        if not line.strip(): continue
        try: parsed.append(json.loads(line))
        except (ValueError,UnicodeDecodeError): malformed+=1
    return parsed,malformed

def stream_bytes(obj):
    if obj.get('encoding')=='utf-8': return obj['text'].encode('utf-8')
    return base64.b64decode(obj['base64'],validate=True)
def visible(response):
    if response.get('ok') is False: return {'error':response['error']}
    if 'schema_version' not in response: return response
    keys=('artifact_id','path','from_line','total_lines','capture_complete','timed_out','output_limit','source','stream','output_scope','spawn_error')
    shown={key:response[key] for key in keys if key in response and response[key] is not None}
    if 'returncode' in response: shown['exit_code']=response['returncode']
    for key in ('stdout','stderr','content'):
        if key in response:
            value=response[key]
            shown[key]=value['text'] if value['encoding']=='utf-8' else {'encoding':'base64','data':value['base64']}
    if response.get('rtk_recall_hashes'): shown['recall_hashes']=response['rtk_recall_hashes']
    if 'artifact_id' in response and 'argv' in response:
        shown['recovery']='Use recover_output with this artifact_id and stream. source=original requests child streams where captured; native recall_hash retrieves stored content where available.'
    return shown

def sdk_visible(item):
    result=item.get('result')
    if not isinstance(result,dict): return None
    parts=[block['text'] for block in result.get('content',[]) if block.get('type')=='text']
    if len(parts)!=1: return None
    try: return json.loads(parts[0])
    except (TypeError,ValueError): return None

def test_counts(data,rust):
    if rust:
        found=re.findall(rb'test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed;',data)
        return [{'passed':int(p),'failed':int(f)} for p,f in found]
    passed=re.findall(rb'(\d+) passing\b',data)
    failed=re.findall(rb'(\d+) failing\b',data)
    return [{'passed':int(passed[-1]),'failed':int(failed[-1]) if failed else 0}] if passed else []

def production(root,rust):
    result={}
    for name in manifest(root):
        path=Path(name)
        selected=(path.parts[0]=='src' and path.suffix=='.rs' and len(path.parts)>1) if rust else (name in {'index.js','posix.js'} or path.parts[0]=='lib' and path.suffix=='.js')
        if selected:
            data=(root/name).read_bytes()
            if rust:
                marker=re.search(rb'(?m)^#\[cfg\(test\)\]\r?\nmod (?:test|tests)\s*\{',data)
                if marker: data=data[:marker.start()]
            result[name]=h(data)
    return result

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-root',type=Path,required=True)
    parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[2],help='Matching evaluator checkout; defaults to this repository')
    parser.add_argument('--output',type=Path,help='New private JSON file; defaults to stdout')
    options=parser.parse_args()
    root=options.run_root.resolve(); project=options.project_root.resolve()
    if not (root/'sessions-complete.json').exists():
        print(json.dumps({'status':'pending_sessions_complete'})); return 2
    plan=read(root/'plan.json'); registration=read(root/'registration.json')
    require(digest(root/'plan.json')==REGISTERED==registration['plan_sha256'],'registration_bytes')
    require(read(root/'sessions-complete.json')['plan_sha256']==REGISTERED,'completion_plan_hash')
    require(read(root/'sessions-complete.json')['planned']==36 and read(root/'sessions-complete.json')['completed']==36,'completion_coverage')
    require(plan['repetitions']==2 and len(plan['trials'])==36,'registered_repetitions_and_trials')
    require({t['id'] for t in plan['tasks']}==set(TASKS),'registered_task_ids')
    expected_order=TASKS.copy(); random.Random(plan['seed']).shuffle(expected_order)
    require(plan['task_order']==expected_order,'seeded_task_order')
    expected=[]
    for position,task in enumerate(expected_order):
        for repetition in (1,2):
            offset=(position+repetition-1)%3
            for arm in ARMS[offset:]+ARMS[:offset]:
                expected.append({'id':f'trial-{len(expected)+1:03d}','task_id':task,'repetition':repetition,'variant':arm})
    require(plan['trials']==expected,'exact_registered_order')
    require(len({x['id'] for x in expected})==36,'unique_trial_ids')
    balance={str(pos+1):dict(Counter(x['variant'] for i,x in enumerate(expected) if i%3==pos)) for pos in range(3)}
    require(all(set(v.values())=={4} for v in balance.values()),'arm_position_balance')
    for name,expected_hash in plan['implementation_sha256'].items():
        require(digest(project/name)==expected_hash,'implementation_hash:'+name)
    for name in ('mini','rtk'):
        require(digest(Path(plan[name]))==plan[name+'_sha256'],'binary_hash:'+name)
    runtime_versions={}
    for program,expected_version in {**plan['tool_versions'],'codex':plan['codex_version']}.items():
        argv=[plan['codex'] if program=='codex' else program,'--version']
        actual=subprocess.run(argv,env=plan['tool_environment'],capture_output=True,check=False).stdout.decode().strip()
        runtime_versions[program]={'matches':actual==expected_version,'registered':expected_version}
        require(actual==expected_version,'runtime_version:'+program)
    for task in TASKS:
        source=root/'sources'/task
        require(manifest(source)==plan['source_files'][task],'source_manifest:'+task)
        require(dependencies(source)==plan['dependency_tree_sha256'][task],'source_dependencies:'+task)
    js_qualification=read(project/'evaluation/debugging/tasks/js/qualification.json')
    js_baselines={row['id']:row['passing_test_count'] for row in js_qualification['checks'] if row['version']=='base' and row['check']=='baseline'}
    js_hidden_hashes={row['id']:(row['stdout_sha256'],row['stderr_sha256']) for row in js_qualification['checks'] if row['version']=='oracle' and row['check']=='hidden'}
    report={'checker_sha256':digest(Path(__file__)), 'schema':1,'checked_utc':datetime.now(timezone.utc).isoformat(),'plan_sha256':REGISTERED,
            'coverage':{'sessions':36,'tasks':6,'repetitions':2,'arms':3,'within_triple_position_counts':balance},
            'runtime_versions':runtime_versions,'trials':[]}
    aggregates=defaultdict(Counter); wall=defaultdict(list); correct={}; graded=0
    prompt_hashes=defaultdict(set); triple_times=defaultdict(list)
    for identity in expected:
        trial=identity['id']; directory=root/'trials'/trial
        result=read(directory/'result.json')
        require(all(result.get(k)==v for k,v in identity.items()),'trial_identity:'+trial)
        require(digest(directory/'events.jsonl')==result['events_sha256'],'events_hash:'+trial)
        require(digest(directory/'prompt.txt')==result['prompt_sha256'],'prompt_hash:'+trial)
        prompt_hashes[identity['task_id']].add(result['prompt_sha256'])
        triple_times[(identity['task_id'],identity['repetition'])].append((result['started_utc'],result['finished_utc']))
        require(result['started_utc']>=plan['registered_utc'],'started_after_registration:'+trial)
        require(digest(directory/'candidate.patch')==result['candidate_patch_sha256'],'patch_hash:'+trial)
        require((directory/'candidate.patch').stat().st_size==result['candidate_patch_bytes'],'patch_length:'+trial)
        require(manifest(directory/'workspace')==result['workspace_files'],'frozen_workspace:'+trial)
        git_env={**os.environ,'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_OPTIONAL_LOCKS':'0','GIT_TERMINAL_PROMPT':'0'}
        patch=subprocess.run(['git','-c','core.hooksPath=/dev/null','diff','--no-ext-diff','--binary','HEAD'],cwd=directory/'workspace',env=git_env,capture_output=True,check=True).stdout
        require(patch==(directory/'candidate.patch').read_bytes(),'patch_matches_frozen_source:'+trial)
        events,malformed=jsonlines(directory/'events.jsonl')
        require(malformed==result['malformed_event_lines']==0,'malformed_events:'+trial)
        completed=[e for e in events if e.get('type')=='turn.completed']
        require(len(completed)==result['turn_completed_count']==1,'one_aggregate_usage:'+trial)
        usage=completed[0].get('usage') if len(completed)==1 else None
        require(usage==result['usage'] and isinstance(usage,dict),'aggregate_usage_matches:'+trial)
        if not isinstance(usage,dict): usage={}
        require(all(type(usage.get(k))==int and usage[k]>=0 for k in ('input_tokens','cached_input_tokens','output_tokens')),'numeric_usage:'+trial)
        require(usage.get('cached_input_tokens',0)<=usage.get('input_tokens',0),'cached_subset:'+trial)
        require(usage.get('reasoning_output_tokens',0)<=usage.get('output_tokens',0),'reasoning_subset:'+trial)
        require(not result['timed_out'] and result['process_exit_code']==0,'successful_cli_exit:'+trial)
        require(not any(e.get('type') in {'error','turn.failed'} for e in events),'no_cli_session_error:'+trial)
        thread=[e['thread_id'] for e in events if e.get('type')=='thread.started']
        require(len(thread)==1 and thread[0]==result['thread_id'],'fresh_thread_receipt:'+trial)
        for event in events:
            item=event.get('item',{})
            require(not(event.get('type')=='item.completed' and item.get('type') in {'command_execution','file_change','web_search'}),'native_bypass:'+trial)
            if item.get('type')=='mcp_tool_call': require(item.get('server')=='sprint','outside_mcp:'+trial)
        calls=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
        logs,bad=jsonlines(directory/'artifacts/tools.jsonl')
        require(bad==0 and len(logs)==len(calls)==result['mcp_calls'],'mcp_call_coverage:'+trial)
        require([x['index'] for x in logs]==list(range(1,len(logs)+1)),'mcp_log_indices:'+trial)
        commands=directory/'artifacts/commands'
        terminal_receipts,bad=jsonlines(commands/'events.jsonl')
        require(bad==0,'terminal_audit_json:'+trial)
        receipt_by_id={r['action_id']:r for r in terminal_receipts}
        require(len(receipt_by_id)==len(terminal_receipts),'unique_terminal_actions:'+trial)
        session=read(commands/'session.json')
        require(session['mode']==identity['variant'],'terminal_arm:'+trial)
        require(session['mini_sha256']==plan['mini_sha256'] and session['rtk_sha256']==plan['rtk_sha256'],'terminal_binary_receipts:'+trial)
        call_counts=Counter(); capture_counts=Counter(); artifact_commands={}
        for index,(log,call) in enumerate(zip(logs,calls),1):
            label=trial+':'+str(index)
            call_counts[log['tool']]+=1
            call_counts['visible_errors']+=bool(log['visible'].get('error'))
            args=call.get('arguments'); args=json.loads(args) if isinstance(args,str) else args
            require(call.get('tool')==log['tool'] and args==log['arguments'],'mcp_arguments:'+label)
            require(sdk_visible(call)==log['visible'],'sdk_visible_equality:'+label)
            response=log['response']
            require(visible(response)==log['visible'],'visible_projection:'+label)
            for stream in ('stdout','stderr','content'):
                if isinstance(response.get(stream),dict) and 'sha256' in response[stream]:
                    data=stream_bytes(response[stream]); counts['stream_values']+=1
                    require(len(data)==response[stream]['bytes'] and h(data)==response[stream]['sha256'],'stream_value_hash:'+label+':'+stream)
            if 'schema_version' in response:
                action=response['action_id']; receipt=receipt_by_id.get(action)
                require(receipt is not None and receipt['response_sha256']==jhash(response),'terminal_response_receipt:'+label)
                require(receipt is not None and receipt['request']=={'action':{'terminal':'run','read_file':'read','recover_output':'recover'}[log['tool']],**({'lines':200,**log['arguments']} if log['tool']=='read_file' else log['arguments'])},'terminal_request_receipt:'+label)
                if 'returncode' in response and ('stdout' in response or 'stderr' in response):
                    action_dir=commands/action; metadata=read(action_dir/'metadata.json')
                    require(all(metadata.get(k)==v for k,v in response.items() if k not in {'ok','stdout','stderr','schema_version','action_id','mode','recovery_requests','action_wall_seconds'}),'capture_metadata:'+label)
                    for stream in ('stdout','stderr'):
                        capture=action_dir/stream; counts['captured_files']+=1
                        require(capture.read_bytes()==stream_bytes(response[stream]),'capture_bytes:'+label+':'+stream)
                    capture_counts['commands' if log['tool']=='terminal' else 'native_recall']+=1
                    capture_counts['nonzero_exit']+=response['returncode']!=0
                    if log['tool']=='terminal':
                        requested=log['arguments']['argv']; launched=response['launched_argv']; route=response['route']
                        capture_counts['route_'+route]+=1
                        expected_launch=requested if identity['variant']=='raw' else ([plan['mini'],'--record',str(action_dir/'record'),'--',*requested] if identity['variant']=='mini' else ([plan['rtk'],*requested] if route=='native' else [plan['rtk'],'run','--',*requested]))
                        require(launched==expected_launch,'wrapper_launch:'+label)
                    capture_counts['incomplete']+=not response['capture_complete']
                    capture_counts['timed_out']+=response['timed_out']
                    capture_counts['output_limit']+=response['output_limit']
                    if log['tool']=='terminal': artifact_commands[response['artifact_id']]=action_dir
                    if identity['variant']=='mini' and log['tool']=='terminal':
                        record=action_dir/'record'; recorded=read(record/'metadata.json')
                        require(recorded['complete']==response['mini_record_complete'],'mini_complete_receipt:'+label)
                        require(recorded['exit_code']==response['returncode'],'mini_exit_receipt:'+label)
                        require(recorded['argv_hex']==[os.fsencode(x).hex() for x in log['arguments']['argv']],'mini_original_argv:'+label)
                        for stream in ('stdout','stderr'):
                            raw=(record/(stream+'.raw')).read_bytes(); filtered=(record/(stream+'.filtered')).read_bytes()
                            counts['mini_record_files']+=2
                            require(len(raw)==recorded[stream+'_raw_bytes'],'mini_raw_length:'+label+':'+stream)
                            require(len(filtered)==recorded[stream+'_filtered_bytes'],'mini_filtered_length:'+label+':'+stream)
                            require(filtered==(action_dir/stream).read_bytes(),'mini_filtered_capture_equality:'+label+':'+stream)
            if log['tool']=='recover_output' and response.get('ok') and 'content' in response and 'artifact_id' in response:
                source=artifact_commands[response['artifact_id']]
                name=response['stream']; original=response['source']=='original'
                original_file=source/'record'/(name+'.raw') if original and identity['variant']=='mini' else source/name
                full=original_file.read_bytes(); args=log['arguments']
                parts=full.split(b'\n'); lines=[x+b'\n' for x in parts[:-1]]+([parts[-1]] if parts[-1] else [])
                start=args.get('from_line',1)-1; end=None if args.get('lines') is None else start+args['lines']
                require(b''.join(lines[start:end])==stream_bytes(response['content']),'recovery_selected_bytes:'+label)
        require(len(terminal_receipts)==sum('schema_version' in x['response'] for x in logs),'terminal_receipt_coverage:'+trial)
        require(len(logs)<=plan['max_actions'],'action_budget:'+trial)
        require(capture_counts['incomplete']==0 and capture_counts['timed_out']==0 and capture_counts['output_limit']==0,'complete_command_captures:'+trial)
        argv=read(directory/'argv.json')
        require('--dangerously-bypass-approvals-and-sandbox' not in argv and '--sandbox' in argv and argv[argv.index('--sandbox')+1]=='workspace-write','cli_permissions:'+trial)
        require('--ephemeral' in argv and '--ignore-user-config' in argv,'fresh_cli_flags:'+trial)
        settings={}
        for index,arg in enumerate(argv[:-1]):
            if arg=='-c':
                key,value=argv[index+1].split('=',1); settings[key]=json.loads(value)
        require(settings.get('model')==plan['model'] and settings.get('model_reasoning_effort')==plan['reasoning_effort'],'model_settings:'+trial)
        require(settings.get('approval_policy')=='never' and settings.get('web_search')=='disabled' and settings.get('project_doc_max_bytes')==0,'cli_isolation_settings:'+trial)
        require([argv[i+1] for i,arg in enumerate(argv[:-1]) if arg=='--disable']==plan['features_disabled'],'disabled_features:'+trial)
        config=read(directory/'config.json')
        require(config['mode']==identity['variant'] and config['env']==plan['tool_environment'],'trial_tool_environment:'+trial)
        language='rust' if identity['task_id'].startswith('R') else 'javascript'
        measured={**{k:usage.get(k,0) for k in ('input_tokens','cached_input_tokens','cache_write_input_tokens','output_tokens','reasoning_output_tokens')},
                  'total_input_plus_output':usage.get('input_tokens',0)+usage.get('output_tokens',0),
                  'uncached_input_plus_output':usage.get('input_tokens',0)-usage.get('cached_input_tokens',0)+usage.get('output_tokens',0),
                  'tool_calls':len(logs),'terminal_calls':call_counts['terminal'],'recovery_calls':call_counts['recover_output'],'read_calls':call_counts['read_file']}
        for group in ('all',language):
            aggregates[(identity['variant'],group)].update(measured); aggregates[(identity['variant'],group)]['sessions']+=1
            wall[(identity['variant'],group)].append(result['wall_seconds'])
        row={**identity,'language':language,'usage':usage,'measured':measured,'wall_seconds':result['wall_seconds'],'tool_counts':dict(call_counts),'capture_counts':dict(capture_counts),'patch_sha256':result['candidate_patch_sha256'],'workspace_manifest_sha256':jhash(result['workspace_files'])}
        evaluation_file=directory/'evaluation/evaluation.json'
        if evaluation_file.exists():
            evaluation=read(evaluation_file); graded+=1
            row['evaluation']={'correct_repair':evaluation['correct_repair'],'production_changed':evaluation['production_changed'],'infrastructure_error_count':len(evaluation['infrastructure_errors']),'checks':{}}
            require(evaluation['frozen_workspace_unchanged'],'evaluation_freeze:'+trial)
            require(input_tree_hash(root/'sources'/identity['task_id'])==evaluation['input_tree_hashes']['base'],'grading_base_input_hash:'+trial)
            require(input_tree_hash(directory/'workspace')==evaluation['input_tree_hashes']['candidate'],'grading_candidate_input_hash:'+trial)
            require(evaluation['task_id']==identity['task_id'],'evaluation_identity:'+trial)
            ep=directory/'evaluation/candidate.patch'
            require(digest(ep)==evaluation['patch']['sha256'] and ep.stat().st_size==evaluation['patch']['bytes'],'evaluation_patch_receipt:'+trial)
            pristine=directory/'evaluation/pristine'; baseline=root/'sources'/identity['task_id']
            require(production(pristine,language=='rust')==production(directory/'workspace',language=='rust'),'scored_production_matches_candidate:'+trial)
            for name,original_hash in manifest(baseline).items():
                path=Path(name)
                is_production=(path.parts[0]=='src' and path.suffix=='.rs' and len(path.parts)>1) if language=='rust' else (name in {'index.js','posix.js'} or path.parts[0]=='lib' and path.suffix=='.js')
                if not is_production:
                    require((pristine/name).exists() and digest(pristine/name)==original_hash,'pristine_original_file:'+trial)
                elif language=='rust':
                    original=(baseline/name).read_bytes(); restored=(pristine/name).read_bytes()
                    marker=re.search(rb'(?m)^#\[cfg\(test\)\]\r?\nmod (?:test|tests)\s*\{',original)
                    if marker: require(restored.endswith(original[marker.start():]),'pristine_original_rust_tests:'+trial)
            require(evaluation['production_changed']==(production(root/'sources'/identity['task_id'],language=='rust')!=production(directory/'workspace',language=='rust')),'production_change:'+trial)
            for name,check in evaluation['checks'].items():
                check_dir=directory/'evaluation'/name.replace('_','-')
                data=b''
                for stream in ('stdout','stderr'):
                    captured=(check_dir/stream).read_bytes(); data+=captured
                    require(len(captured)==check['streams'][stream]['bytes'] and h(captured)==check['streams'][stream]['sha256'],'grading_capture_hash:'+trial+':'+name+':'+stream)
                derived=check['exit_code']==0 and not check['timed_out'] and check['spawn_error'] is None
                require(derived==check['passed'],'grading_check_status:'+trial+':'+name)
                parsed=test_counts(data,language=='rust')
                if name=='pristine_baseline' and check['passed']:
                    count={'R1':19,'R2':19,'R3':38}.get(identity['task_id'],js_baselines.get(identity['task_id']))
                    require(len(parsed)==1 and parsed[0]=={'passed':count,'failed':0},'pristine_baseline_count:'+trial)
                if name=='hidden' and check['passed'] and language=='rust':
                    count={'R1':5,'R2':6,'R3':6}[identity['task_id']]
                    require(any(x=={'passed':count,'failed':0} for x in parsed),'hidden_count:'+trial)
                if name=='hidden' and check['passed'] and language=='javascript':
                    require(tuple(check['streams'][stream]['sha256'] for stream in ('stdout','stderr'))==js_hidden_hashes[identity['task_id']],'hidden_qualification_log_hash:'+trial)
                row['evaluation']['checks'][name]={'passed':derived,'exit_code':check['exit_code'],'test_counts':parsed}
            expected_correct=evaluation['production_changed'] and not evaluation['restore_errors'] and all(evaluation['checks'].get(k,{}).get('passed',False) for k in ('candidate_baseline','pristine_baseline','hidden')) and evaluation['frozen_workspace_unchanged']
            require(expected_correct==evaluation['correct_repair'],'correctness_recomputed:'+trial)
            correct[(identity['task_id'],identity['repetition'],identity['variant'])]=expected_correct
        report['trials'].append(row)
    require(len({row['id'] for row in report['trials']})==36,'audited_coverage')
    require(all(len(values)==1 for values in prompt_hashes.values()),'identical_prompt_per_task')
    for values in triple_times.values():
        require(len(values)==3 and all(before[1]<=after[0] for before,after in zip(values,values[1:])),'observed_sequential_triple_order')
    threads=[read(root/'trials'/identity['id']/'result.json')['thread_id'] for identity in expected]
    require(len(set(threads))==36,'36_unique_threads')
    report['totals']={arm:{group:{**dict(aggregates[(arm,group)]),'wall_seconds_total':sum(wall[(arm,group)]),'wall_seconds_median':statistics.median(wall[(arm,group)])} for group in ('all','rust','javascript')} for arm in ARMS}
    report['resource_reduction_mini_vs_rtk']={group:1-aggregates[('mini',group)]['total_input_plus_output']/aggregates[('rtk',group)]['total_input_plus_output'] for group in ('all','rust','javascript')}
    report['graded_trials']=graded
    if graded==36:
        score={arm:sum(correct[(task,rep,arm)] for task in TASKS for rep in (1,2)) for arm in ARMS}
        mini_wins=[task for task in TASKS if all(correct[(task,rep,'mini')] and not correct[(task,rep,'rtk')] for rep in (1,2))]
        rtk_wins=[task for task in TASKS if all(correct[(task,rep,'rtk')] and not correct[(task,rep,'mini')] for rep in (1,2))]
        by_language={language:{arm:sum(correct[(task,rep,arm)] for task in tasks for rep in (1,2)) for arm in ARMS} for language,tasks in [('rust',TASKS[:3]),('javascript',TASKS[3:])]}
        reductions=report['resource_reduction_mini_vs_rtk']
        gate1=len(mini_wins)>=2 and not rtk_wins
        gate2=reductions['all']>=.2 and score['mini']>=max(score['rtk'],score['raw']) and reductions['rust']>0 and reductions['javascript']>0
        report['decisions']={'correct_repairs':score,'correct_repairs_by_language':by_language,'consistent_mini_win_tasks':mini_wins,'consistent_rtk_win_tasks':rtk_wins,'task_advantage_gate':gate1,'resource_advantage_gate':gate2,'continue_compressor':gate1 or gate2,'eligible_without_audit_failures':not failures}
    else: report['decisions']={'status':'pending_all_36_grades'}
    report['audit']={'passed':not failures,'assertion_count':counts['assertions'],'coverage_counts':dict(counts),'failure_count':len(failures),'failures':failures}
    if options.output:
        options.output.parent.mkdir(parents=True,exist_ok=True)
        with options.output.open('x',encoding='utf-8') as output:
            json.dump(report,output,indent=2,sort_keys=True); output.write('\n')
        print(json.dumps({'audit_passed':not failures,'failures':failures,'assertions':counts['assertions'],'graded_trials':graded,'totals':report['totals'],'resource_reduction_mini_vs_rtk':report['resource_reduction_mini_vs_rtk'],'decisions':report['decisions']},sort_keys=True))
    else:
        print(json.dumps(report,indent=2,sort_keys=True))
    return int(bool(failures))
if __name__=='__main__': raise SystemExit(main())
