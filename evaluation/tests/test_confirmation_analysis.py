"""Synthetic confirmation evidence only; no comparative model calls."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

PATH = Path(__file__).resolve().parents[1] / 'confirmation/analyze.py'
spec = importlib.util.spec_from_file_location('confirmation_analysis_under_test', PATH)
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True)+'\n')


class ConfirmationAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.card={'schema':1,'unit':'credits','model':'gpt-6.1-sol','service_tier':'standard',
                   'per_million_tokens':{'uncached_input':'50','cached_input':'2.5','output':'250'},
                   'source_url':'https://learn.chatgpt.com/docs/pricing#token-rates',
                   'fetched_at':'2026-11-07T00:00:00+00:00'}
        tasks=[{'id':task,'prompt':'PRIVATE PROMPT /Users/private/example','baseline_command':['npm','run','unit']} for task in analysis.TASK_IDS]
        trials=[]
        for task in analysis.TASK_IDS:
            for rep in (1,2,3):
                for variant in analysis.VARIANTS:
                    trials.append({'id':f'trial-{len(trials)+1:03d}','task_id':task,'repetition':rep,'variant':variant})
        self.plan={'schema':1,'seed':20261107,'repetitions':3,'tasks':tasks,'trials':trials,
                   'model':'gpt-6.1-sol','reasoning_effort':'ultra','cost_model':self.card}
        write(self.root/'plan.json',self.plan)
        self.plan_hash=analysis.sha((self.root/'plan.json').read_bytes())
        write(self.root/'registration.json',{'plan_sha256':self.plan_hash})
        for trial in trials:
            folder=self.root/'trials'/trial['id']
            factor={'raw':120,'mini':80,'rtk':100}[trial['variant']]
            result={**trial,'plan_sha256':self.plan_hash,'usage':{'input_tokens':factor,'cached_input_tokens':factor//2,'output_tokens':factor//10,'reasoning_output_tokens':factor//20},
                    'usage_complete':True,'model':'gpt-6.1-sol','service_tier':'standard','standard_speed_verified':True,
                    'timed_out':False,'process_exit_code':0,'turn_completed_count':1,'protocol_deviations':[],
                    'session_errors':[],'wall_seconds':5.0,'mcp_calls':0}
            write(folder/'result.json',result)
            write(folder/'argv.json',['/private/secret/codex','exec','--ignore-user-config','--disable','fast_mode','--disable','ultrafast_mode',
                  '-c','model="gpt-6.1-sol"','-c','model_reasoning_effort="ultra"','-c','service_tier="default"'])
            (folder/'artifacts').mkdir();(folder/'artifacts/tools.jsonl').write_text('')
            grade={'task_id':trial['task_id'],'correct_repair':True,'restore_errors':[], 'infrastructure_errors':[],
                   'frozen_workspace_unchanged':True,'added_test_coverage':True,'patch':{'bytes':100},
                   'checks':{name:{'passed':True,'exit_code':0,'timed_out':False,'spawn_error':None}
                             for name in ('candidate_baseline','pristine_baseline','hidden')}}
            write(folder/'evaluation/evaluation.json',grade)

    def tearDown(self): self.temp.cleanup()

    def change(self, trial_id, name, **changes):
        path=self.root/'trials'/trial_id/name;value=json.loads(path.read_text());value.update(changes);write(path,value)

    def test_complete_54_attempt_gate_and_exact_components(self):
        result=analysis.summarize(self.root)
        self.assertTrue(result['coverage']['complete_confirmation'])
        self.assertTrue(result['decision']['continue_compressor_expansion'])
        self.assertEqual(result['all_attempts']['comparisons']['mini_vs_rtk']['total_cost_ratio'],'0.8')
        mini=result['all_attempts']['variants']['mini']
        self.assertEqual(mini['planned_attempts'],18)
        self.assertEqual(mini['successful_repairs'],18)
        self.assertEqual(mini['total_credits'],'0.0738')
        self.assertEqual(mini['total_components'],{'uncached_input':'0.036','cached_input':'0.0018','output':'0.036'})
        self.assertEqual(result['mini_vs_rtk_task_cluster_bootstrap']['upper_97_5_percentile'],'0.8')
        self.assertFalse(result['actual_billed'])
        public=json.dumps(result)
        for forbidden in ['PRIVATE PROMPT','/Users/','/private/secret',str(self.root)]:self.assertNotIn(forbidden,public)

    def test_missing_usage_is_unknown_not_free(self):
        self.change('trial-002','result.json',usage=None)
        result=analysis.summarize(self.root)
        self.assertFalse(result['coverage']['complete_confirmation'])
        mini=result['all_attempts']['variants']['mini']
        self.assertIsNone(mini['total_credits'])
        self.assertIsNotNone(mini['known_attempt_credits_sum'])
        self.assertEqual(mini['planned_attempts'],18)
        self.assertEqual(mini['known_cost_attempts'],17)
        self.assertFalse(result['decision']['repeatable_cost_evidence'])

    def test_missing_attempt_retains_planned_denominator(self):
        (self.root/'trials/trial-002/result.json').unlink()
        result=analysis.summarize(self.root)
        self.assertEqual(result['coverage']['observed_results'],53)
        self.assertIsNone(result['all_attempts']['variants']['mini']['total_credits'])
        self.assertEqual(result['all_attempts']['variants']['mini']['planned_attempts'],18)

    def test_wrong_repair_cost_is_included_and_lower_correctness_blocks_claim(self):
        folder=self.root/'trials/trial-002/evaluation/evaluation.json';grade=json.loads(folder.read_text())
        grade['correct_repair']=False;grade['checks']['hidden']['passed']=False;grade['checks']['hidden']['exit_code']=1;write(folder,grade)
        result=analysis.summarize(self.root)
        self.assertTrue(result['coverage']['complete_confirmation'])
        self.assertEqual(result['all_attempts']['variants']['mini']['total_credits'],'0.0738')
        self.assertEqual(result['all_attempts']['variants']['mini']['successful_repairs'],17)
        self.assertFalse(result['decision']['repeatable_cost_evidence'])
        self.assertFalse(result['decision']['continue_compressor_expansion'])
        self.assertLess(analysis.Decimal(result['successful_attempts_only_secondary']['variants']['mini']['total_credits']),analysis.Decimal('0.0738'))

    def test_protocol_deviation_retains_cost_but_makes_confirmation_inconclusive(self):
        self.change('trial-002','result.json',protocol_deviations=['private arbitrary /Users/secret'])
        result=analysis.summarize(self.root)
        self.assertFalse(result['coverage']['complete_confirmation'])
        self.assertEqual(result['all_attempts']['variants']['mini']['total_credits'],'0.0738')
        self.assertEqual(result['all_attempts']['variants']['mini']['successful_repairs'],17)
        self.assertNotIn('/Users/secret',json.dumps(result))

    def test_forged_speed_boolean_does_not_replace_saved_argv_audit(self):
        path=self.root/'trials/trial-002/argv.json';argv=json.loads(path.read_text());argv[-1]='service_tier="fast"';write(path,argv)
        result=analysis.summarize(self.root)
        self.assertFalse(result['coverage']['complete_confirmation'])
        self.assertIsNone(result['all_attempts']['variants']['mini']['total_credits'])

    def test_missing_grade_and_restoration_errors_are_inconclusive(self):
        (self.root/'trials/trial-002/evaluation/evaluation.json').unlink()
        self.change('trial-005','evaluation/evaluation.json',restore_errors=['private repair structure'])
        result=analysis.summarize(self.root)
        self.assertFalse(result['coverage']['complete_confirmation'])
        self.assertIsNone(result['all_attempts']['variants']['mini']['credits_per_successful_repair'])
        self.assertNotIn('private repair structure',json.dumps(result))

    def test_session_timeout_does_not_price_partial_usage(self):
        self.change('trial-002','result.json',timed_out=True)
        result=analysis.summarize(self.root)
        self.assertFalse(result['coverage']['complete_confirmation'])
        self.assertIsNone(result['all_attempts']['variants']['mini']['total_credits'])

    def test_zero_success_cost_per_success_is_undefined(self):
        for trial in self.plan['trials']:
            if trial['variant']=='mini':
                path=self.root/'trials'/trial['id']/'evaluation/evaluation.json';value=json.loads(path.read_text());value['correct_repair']=False;write(path,value)
        result=analysis.summarize(self.root)
        self.assertIsNone(result['all_attempts']['variants']['mini']['credits_per_successful_repair'])
        self.assertFalse(result['decision']['continue_compressor_expansion'])

    def test_registration_hash_and_duplicate_identity_fail_closed(self):
        write(self.root/'registration.json',{'plan_sha256':'0'*64})
        with self.assertRaises(analysis.AnalysisError):analysis.summarize(self.root)
        write(self.root/'registration.json',{'plan_sha256':self.plan_hash})
        self.change('trial-002','result.json',id='trial-001')
        with self.assertRaises(analysis.AnalysisError):analysis.summarize(self.root)

    def test_bootstrap_can_cross_one_despite_observed_lower_point_estimate(self):
        pairs={task:('0.8','1') for task in analysis.TASK_IDS}
        pairs['C-R1']=('1.8','1')
        result=analysis.cluster_bootstrap(pairs)
        self.assertLess(sum(analysis.Decimal(pair[0]) for pair in pairs.values())/6,1)
        self.assertGreater(analysis.Decimal(result['upper_97_5_percentile']),1)
        self.assertEqual(result['resamples'],20000)
        self.assertEqual(result['repetitions_per_cluster'],3)

    def test_conflicting_fast_feature_and_unquoted_config_proof_rejected(self):
        argv=json.loads((self.root/'trials/trial-001/argv.json').read_text())
        self.assertFalse(analysis._argv_proof(argv+['--enable','fast_mode'],self.plan))
        self.assertFalse(analysis._argv_proof(argv+['-c','features.fast_mode=true'],self.plan))
        self.assertFalse(analysis._argv_proof(argv+['-c','features={"ultrafast_mode":true}'],self.plan))
        self.assertFalse(analysis._argv_proof(argv+['--service-tier','fast'],self.plan))
        self.assertFalse(analysis._argv_proof(argv+['-c','model="other"'],self.plan))

    def test_terminal_command_timeout_can_recover_with_complete_session_cost(self):
        folder=self.root/'trials/trial-002'
        self.change('trial-002','result.json',mcp_calls=1)
        item={'index':1,'tool':'terminal','arguments':{'argv':['npm','run','unit']},
              'response':{'route':'mini-record','timed_out':True,'capture_complete':False,'ok':True},
              'visible':{'timed_out':True,'exit_code':124}}
        (folder/'artifacts/tools.jsonl').write_text(json.dumps(item)+'\n')
        result=analysis.summarize(self.root)
        self.assertTrue(result['coverage']['complete_confirmation'])
        mini=result['all_attempts']['variants']['mini']
        self.assertEqual(mini['total_credits'],'0.0738')
        self.assertEqual(mini['successful_repairs'],18)
        self.assertEqual(mini['tools']['terminal_timeouts'],1)

    def test_candidate_grading_timeout_is_valid_failed_repair_with_known_cost(self):
        path=self.root/'trials/trial-002/evaluation/evaluation.json';grade=json.loads(path.read_text())
        grade['correct_repair']=False
        grade['checks']['candidate_baseline'].update(passed=False,timed_out=True,exit_code=-9)
        write(path,grade)
        result=analysis.summarize(self.root)
        self.assertTrue(result['coverage']['complete_confirmation'])
        mini=result['all_attempts']['variants']['mini']
        self.assertEqual(mini['total_credits'],'0.0738')
        self.assertEqual(mini['successful_repairs'],17)
        self.assertEqual(mini['grading_timeout_attempts'],1)
        self.assertEqual(result['trials'][1]['grade']['grading_timeout_checks'],1)

    def test_missing_ignore_config_flag_is_not_standard_speed_proof(self):
        argv=json.loads((self.root/'trials/trial-001/argv.json').read_text())
        argv.remove('--ignore-user-config')
        self.assertFalse(analysis._argv_proof(argv,self.plan))

    def test_cost_per_success_ratio_uses_exact_totals_at_threshold(self):
        groups={name:{'total_credits':'1','successful_repairs':18,'credits_per_successful_repair':'0.055555555555555555555555555555555555555555555555555'}
                for name in analysis.VARIANTS}
        groups['mini']={'total_credits':'0.9','successful_repairs':18,'credits_per_successful_repair':'0.05'}
        self.assertEqual(analysis._comparison(groups)['mini_vs_rtk']['cost_per_success_ratio'],'0.9')

    def test_inconsistent_grading_exit_status_is_rejected(self):
        path=self.root/'trials/trial-002/evaluation/evaluation.json';grade=json.loads(path.read_text());grade['checks']['hidden']['exit_code']=1;write(path,grade)
        with self.assertRaises(analysis.AnalysisError):analysis.summarize(self.root)

    def test_invalid_metadata_cannot_export_raw_private_values(self):
        self.change('trial-002','result.json',timed_out='/Users/private/invalid')
        self.change('trial-002','evaluation/evaluation.json',added_test_coverage='/Users/private/invalid')
        result=analysis.summarize(self.root)
        self.assertFalse(result['coverage']['complete_confirmation'])
        self.assertNotIn('/Users/private/invalid',json.dumps(result))

    def test_duplicate_plan_combination_is_rejected(self):
        self.plan['trials'][1]={**self.plan['trials'][0],'id':'trial-002'}
        with self.assertRaises(analysis.AnalysisError):analysis._validate_plan(self.plan)


if __name__=='__main__':unittest.main()
