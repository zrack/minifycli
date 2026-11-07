#!/usr/bin/env python3
"""Post-collection independent audit of the canonical 54-attempt confirmation.

This standalone stdlib query imports none of the collector, analyzer, costing,
terminal, or evaluator helpers. It reads existing private evidence, makes no
model/network/account calls, and does not rerun tests or grade repairs. Git diff
and executable --version checks are read-only. New after collection: not part of
the registered runtime. Output contains counts/hashes/credits, never raw source,
model answers, tool output, account identifiers, or private filesystem paths.
"""
from __future__ import annotations
import argparse
import base64
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, localcontext
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import random
import re
import statistics
import subprocess

PLAN_SHA='2f17831952b856d9b98826a547cf6fdf1aee2d8ab16c4553b9ccefbe320ac0b8'
ARMS=('raw','mini','rtk')
TASKS=tuple('C-'+g+str(i) for g in ('R','J') for i in (1,2,3))
EXCLUDED={'.git','node_modules','target','.targetbaseline','.targethidden','__pycache__'}
PROTECTED=('test/**','tests/**','fixtures/**','**/test/**','**/tests/**','**/fixtures/**','**/tests.rs','**/test.rs','Cargo.toml','Cargo.lock','package.json','package-lock.json','pnpm-lock.yaml','yarn.lock','tsconfig*.json','.cargo/**','build.rs')
BOUNDARY='Observed CLI usage priced at published Standard credit rates; not an invoice, subscription cost, attributed account deduction, or USD charge.'
FAILURES=[]
COUNTS=Counter()

def check(condition,code,trial=None):
    COUNTS['assertions']+=1
    if not condition: FAILURES.append(code+(':'+trial if trial else ''))
def digest(data): return hashlib.sha256(data).hexdigest()
def fhash(path): return digest(path.read_bytes())
def read(path): return json.loads(path.read_bytes())
def jhash(value): return digest(json.dumps(value,sort_keys=True,ensure_ascii=True).encode())
def number(value):
    if value is None:return None
    text=format(value,'f');return text.rstrip('0').rstrip('.') if '.' in text else text

def files(root):
    return {p.relative_to(root).as_posix():p for p in sorted(root.rglob('*')) if p.is_file() and not EXCLUDED.intersection(p.relative_to(root).parts)}
def manifest(root): return {name:fhash(path) for name,path in files(root).items()}
def input_hash(root):
    entries=[{'path':name,'sha256':fhash(p),'bytes':p.stat().st_size} for name,p in sorted(files(root).items())]
    return digest(json.dumps(entries,sort_keys=True,separators=(',',':')).encode())
def dependency_hash(root):
    deps=root/'node_modules';values={}
    if deps.exists():
        for p in sorted(deps.rglob('*')):
            if '.cache' in p.relative_to(deps).parts:continue
            if p.is_symlink():values[p.relative_to(deps).as_posix()]='symlink:'+os.readlink(p)
            elif p.is_file():values[p.relative_to(deps).as_posix()]=fhash(p)
    return jhash(values)
def jsonlines(path):
    result=[];bad=0
    for line in path.read_bytes().splitlines():
        if not line.strip():continue
        try:result.append(json.loads(line))
        except (ValueError,UnicodeError):bad+=1
    return result,bad

def raw_stream(value):
    return value['text'].encode('utf-8') if value['encoding']=='utf-8' else base64.b64decode(value['base64'],validate=True)
def shown(response):
    if response.get('ok') is False:return {'error':response['error']}
    if 'schema_version' not in response:return response
    keys=('artifact_id','path','from_line','total_lines','capture_complete','timed_out','output_limit','source','stream','output_scope','spawn_error')
    result={k:response[k] for k in keys if k in response and response[k] is not None}
    if 'returncode' in response:result['exit_code']=response['returncode']
    for k in ('stdout','stderr','content'):
        if k in response:
            v=response[k];result[k]=v['text'] if v['encoding']=='utf-8' else {'encoding':'base64','data':v['base64']}
    if response.get('rtk_recall_hashes'):result['recall_hashes']=response['rtk_recall_hashes']
    if 'artifact_id' in response and 'argv' in response:result['recovery']='Use recover_output with this artifact_id and stream. source=original requests child streams where captured; native recall_hash retrieves stored content where available.'
    return result

def sdk_output(item):
    result=item.get('result')
    blocks=result.get('content',[]) if isinstance(result,dict) else []
    texts=[b['text'] for b in blocks if b.get('type')=='text']
    if len(texts)!=1:return None
    try:return json.loads(texts[0])
    except (ValueError,TypeError):return None

def requested_settings(argv):
    settings={};disabled=set();duplicates=[]
    for index,arg in enumerate(argv[:-1]):
        if arg in ('-c','--config'):
            key,value=argv[index+1].split('=',1)
            if key in settings:duplicates.append(key)
            settings[key]=json.loads(value)
        if arg=='--disable':disabled.add(argv[index+1])
    return settings,disabled,duplicates

def price(usage):
    if not isinstance(usage,dict):return None,None
    if not all(type(usage.get(k)) is int and usage[k]>=0 for k in ('input_tokens','cached_input_tokens','output_tokens')):return None,None
    i,c,o=(usage[k] for k in ('input_tokens','cached_input_tokens','output_tokens'))
    if c>i:return None,None
    reasoning=usage.get('reasoning_output_tokens',usage.get('reasoning_tokens'))
    if reasoning is not None and (type(reasoning) is not int or not 0<=reasoning<=o):return None,None
    writes=usage.get('cache_write_input_tokens')
    if writes is not None and (type(writes) is not int or writes<0):return None,None
    # Independent integer-weight calculation: equivalent to the registered
    # credit rates, without using its component calculator or summation code.
    amount=Decimal(20*(i-c)+c+100*o)/Decimal(400000)
    components={'uncached_input':Decimal(i-c)/Decimal(20000),'cached_input':Decimal(c)/Decimal(400000),'output':Decimal(o)/Decimal(4000)}
    return amount,components

@lru_cache(maxsize=None)
def glob_regex(pattern):
    # Translate the declared path glob grammar; **/ permits zero directories.
    result='';i=0
    while i<len(pattern):
        if pattern[i:i+3]=='**/':result+='(?:.*/)?';i+=3
        elif pattern[i:i+2]=='**':result+='.*';i+=2
        elif pattern[i]=='*':result+='[^/]*';i+=1
        elif pattern[i]=='?':result+='[^/]';i+=1
        else:result+=re.escape(pattern[i]);i+=1
    return re.compile('^'+result+'$')
def production_path(name,task):
    policy=task['evaluation']
    return any(glob_regex(p).fullmatch(name) for p in policy['production_globs']) and not any(glob_regex(p).fullmatch(name) for p in (*PROTECTED,*policy['protected_test_globs']))

def rust_mask(source):
    # Blank comments and literals without moving source offsets; retain LF.
    out=list(source);i=0;n=len(source)
    def blank(a,b):
        for j in range(a,b):
            if source[j]!='\n':out[j]=' '
    while i<n:
        if source.startswith('//',i):
            end=source.find('\n',i);end=n if end<0 else end;blank(i,end);i=end;continue
        if source.startswith('/*',i):
            start=i;i+=2;depth=1
            while i<n and depth:
                if source.startswith('/*',i):depth+=1;i+=2
                elif source.startswith('*/',i):depth-=1;i+=2
                else:i+=1
            blank(start,i);continue
        raw=re.match(r'(?:br|cr|r)(#*)"',source[i:])
        if raw:
            end=source.find('"'+raw[1],i+len(raw[0]));end=n if end<0 else end+1+len(raw[1]);blank(i,end);i=end;continue
        if source[i]=='"':
            start=i;i+=1
            while i<n:
                if source[i]=='\\':i+=2
                elif source[i]=='"':i+=1;break
                else:i+=1
            blank(start,min(i,n));continue
        char=re.match(r"'(?:\\(?:u\{[0-9a-fA-F_]+\}|x[0-9a-fA-F]{2}|.)|[^'\\\r\n])'",source[i:])
        if char:blank(i,i+len(char[0]));i+=len(char[0]);continue
        i+=1
    return ''.join(out)
def balanced(mask,start):
    stack=[{'(':')','[':']','{':'}'}[mask[start]]];i=start+1
    while i<len(mask) and stack:
        c=mask[i]
        if c in '([{':stack.append({'(':')','[':']','{':'}'}[c])
        elif c in ')]}':
            if c!=stack.pop():raise ValueError('unbalanced Rust syntax')
        i+=1
    if stack:raise ValueError('unclosed Rust syntax')
    return i

@lru_cache(maxsize=None)
def rust_parts(data):
    source=data.decode('utf-8');mask=rust_mask(source);attributes=[];cursor=0
    while True:
        hit=re.search(r'#\s*!?\s*\[',mask[cursor:])
        if not hit:break
        start=cursor+hit.start();bracket=cursor+hit.end()-1;end=balanced(mask,bracket)
        attributes.append((start,end,re.sub(r'\s+','',mask[bracket+1:end-1])));cursor=end
    groups=[]
    for item in attributes:
        if groups and not mask[groups[-1][-1][1]:item[0]].strip():groups[-1].append(item)
        else:groups.append([item])
    spans=[];inner=[]
    for group in groups:
        start=group[0][0]
        if spans and start<spans[-1][1]:continue
        attrs=[x[2] for x in group]
        if not any(re.search(r'\btest\b',a) for a in attrs):continue
        if re.match(r'#\s*!',mask[start:group[0][1]]):inner.append(source[start:group[-1][1]]);continue
        if not any(a=='test' or a=='cfg(test)' or a.startswith('cfg(all(') and 'test' in a for a in attrs):continue
        pos=group[-1][1]
        while pos<len(mask):
            if mask[pos] in '([':pos=balanced(mask,pos)
            elif mask[pos] in '{;':break
            else:pos+=1
        if pos==len(mask):raise ValueError('missing protected Rust item')
        end=pos+1 if mask[pos]==';' else balanced(mask,pos)
        spans.append((start,end))
    tests=[source[a:b] for a,b in spans]
    for a,b in reversed(spans):source=source[:a]+source[b:]
    return source.strip().encode(),Counter(tests),inner

def production(root,task):
    result={}
    for name,p in files(root).items():
        if production_path(name,task):result[name]=digest(rust_parts(p.read_bytes())[0] if name.endswith('.rs') else p.read_bytes())
    return result

def parse_test_counts(data,rust):
    clean=re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]',b'',data)
    if rust:return [{'passed':int(p),'failed':int(f)} for p,f in re.findall(rb'test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed;',clean)]
    passing=re.findall(rb'(\d+) passing\b',clean)
    failing=re.findall(rb'(\d+) failing\b',clean)
    if passing:return [{'passed':int(passing[-1]),'failed':int(failing[-1]) if failing else 0}]
    plain=clean.decode('utf-8',errors='replace')
    node_passed=re.findall(r'(?m)^(?:#|ℹ)\s+pass\s+(\d+)\s*$',plain)
    node_failed=re.findall(r'(?m)^(?:#|ℹ)\s+fail\s+(\d+)\s*$',plain)
    if node_passed and node_failed:return [{'passed':int(node_passed[-1]),'failed':int(node_failed[-1])}]
    total=re.findall(rb'Total:\s*(\d+)',clean);passed=re.findall(rb'Passed:\s*(\d+)',clean)
    if total and passed:return [{'passed':int(passed[-1]),'failed':int(total[-1])-int(passed[-1])}]
    return []

def aggregate(rows):
    known=[r for r in rows if r['credits'] is not None]
    complete=len(known)==len(rows)
    total=sum((Decimal(r['credits']) for r in known),Decimal(0)) if complete else None
    unknown_correct=sum(r['correct_repair'] is None for r in rows)
    successes=sum(r['correct_repair'] is True for r in rows)
    return {'attempts':len(rows),'known_cost_attempts':len(known),'unknown_correctness':unknown_correct,'successful_repairs':successes,
            'credits':number(total),'known_credit_subtotal':number(sum((Decimal(r['credits']) for r in known),Decimal(0))),
            'credits_per_successful_repair':number(total/successes) if total is not None and successes and not unknown_correct else None,
            'usage':{k:sum(r['usage'].get(k,0) or 0 for r in rows if r['usage']) for k in ('input_tokens','cached_input_tokens','output_tokens','reasoning_output_tokens')},
            'wall_seconds_sum':sum(r['wall_seconds'] for r in rows),'tool_calls':sum(r['tools']['all'] for r in rows),
            'terminal_calls':sum(r['tools'].get('terminal',0) for r in rows),'recovery_calls':sum(r['tools'].get('recover_output',0) for r in rows)}
def ratio(a,b):return Decimal(a)/Decimal(b) if a is not None and b is not None and Decimal(b)!=0 else None

def bootstrap(task_totals):
    if any(task_totals[t][a] is None for t in TASKS for a in ('mini','rtk')):return {'available':False}
    pairs=[(Decimal(task_totals[t]['mini']),Decimal(task_totals[t]['rtk'])) for t in sorted(TASKS)];rng=random.Random(20261107);values=[]
    for _ in range(20000):
        weights=Counter(rng.randrange(6) for _ in range(6))
        mini=sum((pairs[i][0]*count for i,count in weights.items()),Decimal(0));rtk=sum((pairs[i][1]*count for i,count in weights.items()),Decimal(0))
        if not rtk:return {'available':False}
        values.append(mini/rtk)
    values.sort()
    def percentile(p):
        position=Decimal(p)*19999;lo=int(position);hi=min(lo+1,19999)
        return values[lo]+(values[hi]-values[lo])*(position-lo)
    return {'available':True,'task_clusters':6,'repetitions_retained_together':3,'resamples':20000,'seed':20261107,
            'lower_2_5_percentile':number(percentile('0.025')),'upper_97_5_percentile':number(percentile('0.975')),
            'interpretation':'Paired task-cluster stability check for six correlated convenience-sampled tasks; not a population confidence claim.'}

def audit(root,project):
    plan=read(root/'plan.json');receipt=read(root/'registration.json')
    check(fhash(root/'plan.json')==PLAN_SHA==receipt['plan_sha256'],'canonical_registration_bytes')
    for marker,count_name in [('sessions-complete.json','completed'),('grading-complete.json','graded')]:
        value=read(root/marker);check(value['plan_sha256']==PLAN_SHA and value[count_name]==54,'completion_receipt_'+count_name)
    check(plan['model']=='gpt-6.1-sol' and plan['reasoning_effort']=='ultra' and plan['service_tier']=='standard','registered_model_and_speed')
    check(plan['repetitions']==3 and plan['workers']==3 and plan['session_timeout_seconds']==900 and plan['soft_deadline_seconds']==720 and plan['max_actions']==90,'registered_budgets')
    check(plan['cost_model']['per_million_tokens']=={'uncached_input':'50','cached_input':'2.5','output':'250'},'registered_rates')
    check(fhash(project/'evaluation/confirmation/rates/codex-standard-2026-11-06.json')==plan['rate_card_file_sha256'],'rate_card_bytes')
    for name,value in plan['implementation_sha256'].items():check(fhash(project/name)==value,'registered_implementation_hash')
    for name in ('mini','rtk','codex'):check(fhash(Path(plan[name]))==plan[name+'_sha256'],'registered_executable_hash_'+name)
    versions={}
    for name,value in {**plan['tool_versions'],'codex':plan['codex_version']}.items():
        observed=subprocess.run([plan['codex'] if name=='codex' else name,'--version'],env=plan['tool_environment'],capture_output=True,check=False).stdout.decode().strip()
        check(observed==value,'runtime_version_'+name);versions[name]={'registered':value,'matches':observed==value}
    task_map={t['id']:t for t in plan['tasks']};check(set(task_map)==set(TASKS),'six_registered_tasks')
    rng=random.Random(20261107);expected=[];blocks=[]
    for repetition in (1,2,3):
        ordered=sorted(TASKS);rng.shuffle(ordered);blocks.append(ordered)
        for task in ordered:
            offset=(sorted(TASKS).index(task)+repetition-1)%3
            for arm in ARMS[offset:]+ARMS[:offset]:expected.append({'id':f'trial-{len(expected)+1:03d}','task_id':task,'repetition':repetition,'variant':arm})
    check(expected==plan['trials'] and blocks==plan['repetition_blocks'],'registered_schedule_and_blocks')
    for task in TASKS:
        check(manifest(root/'sources'/task)==plan['source_files'][task],'registered_source_'+task)
        check(dependency_hash(root/'sources'/task)==plan['dependency_tree_sha256'][task],'registered_dependencies_'+task)
    jsq=read(project/'evaluation/confirmation/tasks/js/qualification.json')
    base_counts={'C-R1':193,'C-R2':223,'C-R3':18,**{r['id']:r['test_count'] for r in jsq['checks'] if r['version']=='base' and r['check']=='baseline'}}
    js_hidden={r['id']:{k:r[k]['sha256'] for k in ('stdout','stderr')} for r in jsq['checks'] if r['version']=='oracle' and r['check']=='hidden'}
    rows=[];threads=[];prompt_hashes=defaultdict(set);triple_times=defaultdict(list)
    for identity in expected:
        ident=identity['id'];directory=root/'trials'/ident;result=read(directory/'result.json');task=task_map[identity['task_id']]
        check(all(result.get(k)==v for k,v in identity.items()) and result['plan_sha256']==PLAN_SHA,'result_identity',ident)
        for name,key in [('events.jsonl','events_sha256'),('prompt.txt','prompt_sha256'),('candidate.patch','candidate_patch_sha256')]:check(fhash(directory/name)==result[key],'frozen_'+key,ident)
        check((directory/'candidate.patch').stat().st_size==result['candidate_patch_bytes'],'patch_length',ident)
        check(manifest(directory/'workspace')==result['workspace_files'],'frozen_workspace_manifest',ident)
        env={**os.environ,'GIT_OPTIONAL_LOCKS':'0','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0'}
        patch=subprocess.run(['git','-c','core.hooksPath=/dev/null','diff','--no-ext-diff','--binary','HEAD'],cwd=directory/'workspace',env=env,capture_output=True,check=True).stdout
        check(patch==(directory/'candidate.patch').read_bytes(),'patch_matches_frozen_source',ident)
        check(read(directory/'build-cleanup.json')['source_and_captures_preserved'] and not (directory/'workspace/target').exists(),'disposable_build_cleanup',ident)
        argv=read(directory/'argv.json');settings,disabled,duplicates=requested_settings(argv)
        check(not duplicates,'unique_cli_settings',ident)
        speed_ok=(settings.get('model')==plan['model'] and settings.get('model_reasoning_effort')=='ultra' and settings.get('service_tier')=='default' and {'fast_mode','ultrafast_mode'}<=disabled and settings.get('features.fast_mode',False) is False and settings.get('features.ultrafast_mode',False) is False)
        check(speed_ok and result['standard_speed_verified'] and result['model']==plan['model'] and result['service_tier']=='standard','requested_standard_alias_and_effort',ident)
        check('--ignore-user-config' in argv and '--ephemeral' in argv and '--dangerously-bypass-approvals-and-sandbox' not in argv and argv[argv.index('--sandbox')+1]=='workspace-write','fresh_safe_cli_flags',ident)
        config=read(directory/'config.json');check(config['env']==plan['tool_environment'] and config['mode']==identity['variant'],'command_environment_registration',ident)
        effective=read(directory/'artifacts/command-environment.json');unset=task['setup'].get('environment_unset',[])
        check(effective['declared_unset']==unset and config['environment_unset']==unset,'declared_color_exception',ident)
        check(('NO_COLOR' not in effective['effective_keys']) if identity['task_id']=='C-J3' else ('NO_COLOR' in effective['effective_keys']),'effective_NO_COLOR_policy',ident)
        events,bad=jsonlines(directory/'events.jsonl');completed=[e for e in events if e.get('type')=='turn.completed'];errors=[e for e in events if e.get('type') in ('error','turn.failed')]
        check(bad==result['malformed_event_lines'],'malformed_event_accounting',ident)
        check(len(completed)==result['turn_completed_count'],'final_aggregate_count',ident)
        usage=completed[0].get('usage') if len(completed)==1 else None
        check(usage==result['usage'],'aggregate_usage_exact_once',ident)
        complete=not result['timed_out'] and result['process_exit_code']==0 and len(completed)==1 and not bad and usage is not None and not errors
        check(complete==result['usage_complete'],'complete_telemetry_flag',ident)
        for event in events:
            item=event.get('item',{})
            check(not(event.get('type')=='item.completed' and item.get('type') in ('command_execution','file_change','web_search')),'no_native_bypass',ident)
            if item.get('type')=='mcp_tool_call':check(item.get('server')=='sprint','only_registered_mcp',ident)
        thread=[e['thread_id'] for e in events if e.get('type')=='thread.started'];check(len(thread)==1 and thread[0]==result['thread_id'],'fresh_thread',ident);threads.extend(thread)
        prompt_hashes[identity['task_id']].add(result['prompt_sha256']);triple_times[(identity['task_id'],identity['repetition'])].append((result['started_utc'],result['finished_utc']))
        check(result['started_utc']>=plan['registered_utc'],'started_after_registration',ident)
        logs,malformed=jsonlines(directory/'artifacts/tools.jsonl');calls=[e['item'] for e in events if e.get('type')=='item.completed' and e.get('item',{}).get('type')=='mcp_tool_call']
        check(not malformed and len(logs)==len(calls)==result['mcp_calls'],'all_mcp_results_retained',ident)
        check([x['index'] for x in logs]==list(range(1,len(logs)+1)),'sequential_tool_indices',ident)
        commands=directory/'artifacts/commands';receipts,malformed=jsonlines(commands/'events.jsonl');by_action={x['action_id']:x for x in receipts}
        check(not malformed and len(by_action)==len(receipts),'terminal_receipt_uniqueness',ident)
        session=read(commands/'session.json');check(session['mode']==identity['variant'] and session['mini_sha256']==plan['mini_sha256'] and session['rtk_sha256']==plan['rtk_sha256'],'terminal_binary_receipts',ident)
        tools=Counter();capture=Counter();artifacts={};max_visible=0
        for log,call in zip(logs,calls):
            tools[log['tool']]+=1;tools['all']+=1
            args=call.get('arguments');args=json.loads(args) if isinstance(args,str) else args
            check(call.get('tool')==log['tool'] and args==log['arguments'],'sdk_request_equality',ident)
            check(sdk_output(call)==log['visible'],'sdk_output_exact_no_truncation',ident);COUNTS['sdk_outputs_checked']+=1
            response=log['response'];check(shown(response)==log['visible'],'visible_projection',ident)
            max_visible=max(max_visible,len(json.dumps(log['visible'],ensure_ascii=False).encode()))
            if log['index']>90:check('error' in log['visible'],'budget_rejection_after_limit',ident)
            for stream in ('stdout','stderr','content'):
                if isinstance(response.get(stream),dict) and 'sha256' in response[stream]:
                    data=raw_stream(response[stream]);check(len(data)==response[stream]['bytes'] and digest(data)==response[stream]['sha256'],'returned_stream_hash',ident);COUNTS['returned_stream_values']+=1
            if 'schema_version' not in response:continue
            action=response['action_id'];receipt=by_action.get(action)
            check(receipt is not None and receipt['response_sha256']==jhash(response),'terminal_response_hash',ident)
            expected_request={'action':{'terminal':'run','read_file':'read','recover_output':'recover'}[log['tool']],**({'lines':200,**log['arguments']} if log['tool']=='read_file' else log['arguments'])}
            check(receipt is not None and receipt['request']==expected_request,'terminal_request_receipt',ident)
            if 'returncode' in response and 'stdout' in response:
                action_dir=commands/action;metadata=read(action_dir/'metadata.json')
                check(all(metadata.get(k)==v for k,v in response.items() if k not in ('ok','stdout','stderr','schema_version','action_id','mode','recovery_requests','action_wall_seconds')),'capture_metadata',ident)
                for stream in ('stdout','stderr'):
                    check((action_dir/stream).read_bytes()==raw_stream(response[stream]),'captured_bytes_equality',ident);COUNTS['capture_stream_files']+=1
                capture['commands' if log['tool']=='terminal' else 'native_recall']+=1;capture['timed_out']+=bool(response['timed_out']);capture['incomplete']+=not response['capture_complete'];capture['output_limit']+=bool(response['output_limit'])
                if log['tool']=='terminal':
                    artifacts[response['artifact_id']]=action_dir;requested=log['arguments']['argv'];route=response['route'];capture['route_'+route]+=1
                    launched=requested if identity['variant']=='raw' else ([plan['mini'],'--record',str(action_dir/'record'),'--',*requested] if identity['variant']=='mini' else ([plan['rtk'],*requested] if route=='native' else [plan['rtk'],'run','--',*requested]))
                    check(response['launched_argv']==launched,'registered_wrapper_argv',ident)
                    if identity['variant']=='mini':
                        record=action_dir/'record';m=read(record/'metadata.json');check(m['complete']==response['mini_record_complete'] and m['exit_code']==response['returncode'],'mini_record_receipt',ident)
                        check(m['argv_hex']==[os.fsencode(v).hex() for v in requested],'mini_original_argv',ident)
                        for stream in ('stdout','stderr'):
                            original=(record/(stream+'.raw')).read_bytes();filtered=(record/(stream+'.filtered')).read_bytes()
                            check(len(original)==m[stream+'_raw_bytes'] and len(filtered)==m[stream+'_filtered_bytes'],'mini_record_lengths',ident)
                            check(filtered==(action_dir/stream).read_bytes(),'mini_filtered_exact_capture',ident);COUNTS['mini_record_files']+=2
            if log['tool']=='recover_output' and response.get('ok') and 'content' in response and 'artifact_id' in response:
                origin=artifacts[response['artifact_id']];stream=response['stream'];raw=response['source']=='original'
                path=origin/'record'/(stream+'.raw') if raw and identity['variant']=='mini' else origin/stream
                full=path.read_bytes();parts=full.split(b'\n');lines=[x+b'\n' for x in parts[:-1]]+([parts[-1]] if parts[-1] else []);args=log['arguments'];start=args.get('from_line',1)-1;end=None if args.get('lines') is None else start+args['lines']
                check(b''.join(lines[start:end])==raw_stream(response['content']),'recovery_exact_selection',ident)
        check(len(receipts)==sum('schema_version' in x['response'] for x in logs),'terminal_receipt_coverage',ident)
        amount,components=price(usage)
        if not complete or not speed_ok:amount,components=None,None
        if usage is not None:
            check(usage.get('reasoning_output_tokens') is None or type(usage['reasoning_output_tokens']) is int and 0<=usage['reasoning_output_tokens']<=usage['output_tokens'],'reasoning_is_output_subset',ident)
        evaluation=read(directory/'evaluation/evaluation.json');checks={};infrastructure=bool(evaluation['restore_errors'] or evaluation['infrastructure_errors'])
        check(evaluation['task_id']==identity['task_id'] and evaluation['frozen_workspace_unchanged'] and evaluation['base_unchanged'],'grading_identity_and_frozen_inputs',ident)
        check(input_hash(root/'sources'/identity['task_id'])==evaluation['input_tree_hashes']['base'] and input_hash(directory/'workspace')==evaluation['input_tree_hashes']['candidate'],'grading_input_tree_hashes',ident)
        ep=directory/'evaluation/candidate.patch';check(fhash(ep)==evaluation['patch']['sha256'] and ep.stat().st_size==evaluation['patch']['bytes'],'grading_patch_receipt',ident)
        original=root/'sources'/identity['task_id'];pristine=directory/'evaluation/pristine'
        if not infrastructure:
            original_production=production(original,task);candidate_production=production(directory/'workspace',task);scored_production=production(pristine,task)
            check((original_production!=candidate_production)==evaluation['production_changed'],'independent_production_change',ident)
            check(candidate_production==scored_production,'scored_production_matches_candidate',ident)
            for name,path in files(original).items():
                if not production_path(name,task):check((pristine/name).exists() and fhash(pristine/name)==fhash(path),'pristine_original_nonproduction_file',ident)
                elif name.endswith('.rs'):
                    _,tests,attrs=rust_parts(path.read_bytes());_,restored,restored_attrs=rust_parts((pristine/name).read_bytes())
                    check(tests==restored and attrs==restored_attrs,'pristine_original_rust_test_items',ident)
        for name in ('candidate_baseline','pristine_baseline','hidden'):
            item=evaluation['checks'].get(name)
            if item is None:checks[name]={'present':False};infrastructure=True;continue
            observed_pass=item['exit_code']==0 and not item['timed_out'] and item['spawn_error'] is None
            check(observed_pass==item['passed'],'grading_status_from_exit',ident)
            stage=directory/'evaluation'/name.replace('_','-');data=b''
            for stream in ('stdout','stderr'):
                content=(stage/stream).read_bytes();data+=content
                check(len(content)==item['streams'][stream]['bytes'] and digest(content)==item['streams'][stream]['sha256'],'grading_capture_bytes',ident);COUNTS['grading_stream_files']+=1
            parsed=parse_test_counts(data,identity['task_id'].startswith('C-R'))
            if name=='pristine_baseline' and observed_pass:check(parsed==[{'passed':base_counts[identity['task_id']],'failed':0}],'original_baseline_test_count',ident)
            if name=='hidden' and observed_pass:
                if identity['task_id'].startswith('C-R'):check(parsed==[{'passed':task['hidden_test_counts']['total'],'failed':0}],'held_out_test_count',ident)
                else:check(all(item['streams'][s]['sha256']==js_hidden[identity['task_id']][s] for s in ('stdout','stderr')),'held_out_qualified_log_hash',ident)
            clean=item['target_cleanup'];check(clean['error_type'] is None and (not clean['created'] or clean['removed']),'evaluation_target_cleanup',ident)
            if item['spawn_error'] is not None:infrastructure=True
            checks[name]={'present':True,'passed':observed_pass,'exit_code':item['exit_code'],'timed_out':item['timed_out'],'test_counts':parsed}
        expected_correct=evaluation['production_changed'] and not infrastructure and all(checks.get(n,{}).get('passed',False) for n in ('candidate_baseline','pristine_baseline','hidden'))
        check(expected_correct==evaluation['correct_repair'],'correctness_recomputed',ident)
        correct=None if infrastructure else bool(expected_correct and not result['protocol_deviations'] and not result['timed_out'] and result['process_exit_code']==0)
        operational=complete and speed_ok and amount is not None and not result['protocol_deviations'] and not infrastructure
        rows.append({**identity,'language':'rust' if identity['task_id'].startswith('C-R') else 'javascript','usage':usage,'credits':number(amount),'components':{k:number(v) for k,v in components.items()} if components else None,'operational_complete':operational,'correct_repair':correct,'checks':checks,'wall_seconds':result['wall_seconds'],'tools':dict(tools),'captures':dict(capture),'maximum_visible_response_bytes':max_visible,'workspace_manifest_sha256':jhash(result['workspace_files']),'patch_sha256':result['candidate_patch_sha256']})
    check(len(rows)==54 and len(set(threads))==54,'all_54_unique_sessions')
    check(all(len(values)==1 for values in prompt_hashes.values()),'same_prompt_per_task')
    for times in triple_times.values():check(len(times)==3 and all(a[1]<=b[0] for a,b in zip(times,times[1:])),'observed_sequential_triple_order')
    totals={a:aggregate([r for r in rows if r['variant']==a]) for a in ARMS}
    languages={lang:{a:aggregate([r for r in rows if r['variant']==a and r['language']==lang]) for a in ARMS} for lang in ('rust','javascript')}
    tasks={t:{a:aggregate([r for r in rows if r['variant']==a and r['task_id']==t]) for a in ARMS} for t in TASKS}
    task_costs={t:{a:tasks[t][a]['credits'] for a in ARMS} for t in TASKS}
    all_complete=all(r['operational_complete'] for r in rows)
    interval=bootstrap(task_costs) if all_complete else {'available':False,'reason':'incomplete_operational_coverage'}
    comparisons={}
    for arm in ('raw','rtk'):
        mini,other=totals['mini'],totals[arm]
        per_success=None
        if mini['credits'] is not None and other['credits'] is not None and mini['successful_repairs'] and other['successful_repairs'] and not mini['unknown_correctness'] and not other['unknown_correctness']:
            per_success=ratio(Decimal(mini['credits'])*other['successful_repairs'],Decimal(other['credits'])*mini['successful_repairs'])
        comparisons[arm]={'total_cost_ratio':number(ratio(mini['credits'],other['credits'])),'cost_per_success_ratio':number(per_success)}
    leave_out={}
    for omitted in TASKS:
        mini=aggregate([r for r in rows if r['variant']=='mini' and r['task_id']!=omitted]);rtk=aggregate([r for r in rows if r['variant']=='rtk' and r['task_id']!=omitted]);leave_out[omitted]=number(ratio(mini['credits'],rtk['credits']))
    below=lambda value:value is not None and Decimal(value)<1
    criteria={'all_54_attempts_usable':all_complete,'correctness_no_lower_than_raw_and_rtk':all(totals['mini']['successful_repairs']>=totals[a]['successful_repairs'] for a in ('raw','rtk')),'bootstrap_upper_below_one':interval['available'] and below(interval.get('upper_97_5_percentile')),'total_cost_at_least_10_percent_lower':comparisons['rtk']['total_cost_ratio'] is not None and Decimal(comparisons['rtk']['total_cost_ratio'])<=Decimal('.9'),'cost_per_success_at_least_10_percent_lower':comparisons['rtk']['cost_per_success_ratio'] is not None and Decimal(comparisons['rtk']['cost_per_success_ratio'])<=Decimal('.9'),'both_language_groups_lower':all(below(number(ratio(languages[l]['mini']['credits'],languages[l]['rtk']['credits']))) for l in languages),'at_least_four_task_totals_lower':sum(below(number(ratio(tasks[t]['mini']['credits'],tasks[t]['rtk']['credits']))) for t in TASKS)>=4,'all_leave_one_task_out_ratios_lower':all(below(v) for v in leave_out.values())}
    evidence=all(criteria[k] for k in ('all_54_attempts_usable','correctness_no_lower_than_raw_and_rtk','bootstrap_upper_below_one'))
    decision={'criteria':criteria,'repeatable_cost_evidence':evidence,'continue_compressor_expansion':all(criteria.values())}
    # Post-collection contract sensitivity: retain the registered primary score.
    # Reaching the first token-shape assertion proves the preceding synchronous
    # rendering assertions completed, without executing any additional test.
    fixture=project/'evaluation/confirmation/tasks/js/C-J2-hidden.mjs'
    fixture_source=fixture.read_text()
    token_assertion=next(i for i,line in enumerate(fixture_source.splitlines(),1) if 'assert.deepEqual(image.children.map(token => token.type)' in line)
    cases_source=fixture_source.split('const cases = [',1)[1].split('\n]',1)[0]
    render_cases=sum(line.lstrip().startswith('[') for line in cases_source.splitlines())
    j2_rows=[row for row in rows if row['task_id']=='C-J2'];render_evidence=[]
    for row in j2_rows:
        stderr=(root/'trials'/row['id']/'evaluation/hidden/stderr').read_text()
        points=[int(n) for n in re.findall(r'C-J2-hidden\.mjs:(\d+):\d+',stderr)]
        proved=(row['checks']['hidden'].get('passed') is False and 'AssertionError' in stderr and points and points[0]==token_assertion)
        render_evidence.append({'id':row['id'],'render_assertions_before_failure':render_cases,'first_failed_fixture_line':points[0] if points else None,'rendering_checks_completed':bool(proved)})
    sensitivity_usable=(len(j2_rows)==9 and all(e['rendering_checks_completed'] for e in render_evidence) and all(row['correct_repair'] is True for row in rows if row['task_id']!='C-J2'))
    caveat={'post_collection':True,'primary_grades_and_gate_unchanged':True,'fixture_sha256':fhash(fixture),'observations':render_evidence,
            'scope':'Rendering-only sensitivity is weaker than the registered full token-shape contract and is not a replacement primary score.',
            'interpretation_limit':'Passing the rendering checks alone does not establish the full metadata/token-shape requirement.',
            'sensitivity_usable':sensitivity_usable,'by_variant':{}}
    if sensitivity_usable:
        for arm in ARMS:
            caveat['by_variant'][arm]={'primary_registered_repairs':totals[arm]['successful_repairs'],'rendering_only_sensitivity_repairs':18,
                                      'all_attempt_credits_unchanged':totals[arm]['credits'],'rendering_only_credits_per_repair':number(Decimal(totals[arm]['credits'])/18)}
        caveat['total_cost_ranking_unchanged']=True
        caveat['cost_per_success_ratio_ranking_unchanged']=True
    agreement=None
    if (root/'summary.json').exists():
        saved=read(root/'summary.json')
        for arm in ARMS:
            check(saved['all_attempts']['variants'][arm]['total_credits']==totals[arm]['credits'],'analyzer_total_cost_'+arm)
            check(saved['all_attempts']['variants'][arm]['successful_repairs']==totals[arm]['successful_repairs'],'analyzer_correctness_'+arm)
            check(abs(Decimal(saved['all_attempts']['variants'][arm]['credits_per_successful_repair'])-Decimal(totals[arm]['credits_per_successful_repair']))<=Decimal('1e-50') if totals[arm]['credits_per_successful_repair'] is not None else saved['all_attempts']['variants'][arm]['credits_per_successful_repair'] is None,'analyzer_success_denominator_'+arm)
        check(saved['decision']['criteria']==criteria and saved['decision']['repeatable_cost_evidence']==evidence and saved['decision']['continue_compressor_expansion']==decision['continue_compressor_expansion'],'analyzer_gate_agreement')
        if interval['available']:check(all(saved['mini_vs_rtk_task_cluster_bootstrap'][k]==interval[k] for k in ('lower_2_5_percentile','upper_97_5_percentile')),'analyzer_bootstrap_agreement')
        agreement=True
    return {'schema':1,'audit_kind':'post-collection-independent-confirmation','checked_utc':datetime.now(timezone.utc).isoformat(),'checker_sha256':fhash(Path(__file__)),'plan_sha256':PLAN_SHA,'cost_boundary':BOUNDARY,'actual_billed':False,'pricing_identity':'(20*(I-C)+C+100*O)/400000 credits; reasoning already in O','coverage':{'planned_attempts':54,'audited_attempts':len(rows),'registered_implementation_files':len(plan['implementation_sha256']),'independent_upstreams':len({t['repository']['url'] for t in plan['tasks']}),'correlated_task_clusters':6,'model_contexts':len(set(threads))},'runtime_versions':versions,'totals':totals,'by_language':languages,'by_task':tasks,'mini_cost_ratios':comparisons,'leave_one_task_out_mini_rtk_ratios':leave_out,'paired_task_cluster_bootstrap':interval,'decision':decision,'analyzer_agreement_checked':agreement,'post_collection_J2_contract_caveat':caveat,'trials':rows,'audit':{'passed':not FAILURES,'assertions':COUNTS['assertions'],'coverage_counts':dict(COUNTS),'failures':FAILURES}}

def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-root',type=Path,required=True);parser.add_argument('--project-root',type=Path,default=Path(__file__).resolve().parents[2]);parser.add_argument('--output',type=Path,help='New JSON file; defaults to stdout; never overwrites')
    options=parser.parse_args();root=options.run_root.resolve()
    if not (root/'sessions-complete.json').exists() or not (root/'grading-complete.json').exists():print(json.dumps({'status':'pending_collection_or_grading_completion'}));return 2
    with localcontext() as context:
        context.prec=60;report=audit(root,options.project_root.resolve())
    if options.output:
        options.output.parent.mkdir(parents=True,exist_ok=True)
        with options.output.open('x',encoding='utf-8') as output:json.dump(report,output,indent=2,sort_keys=True);output.write('\n')
        print(json.dumps({'audit_passed':report['audit']['passed'],'assertions':report['audit']['assertions'],'failures':report['audit']['failures'],'totals':report['totals'],'decision':report['decision']},sort_keys=True))
    else:print(json.dumps(report,indent=2,sort_keys=True))
    return int(not report['audit']['passed'])
if __name__=='__main__':raise SystemExit(main())
