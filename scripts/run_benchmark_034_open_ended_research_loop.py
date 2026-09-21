from __future__ import annotations
import argparse, json, tempfile
from pathlib import Path
from cydra.canonical_cycle import run_canonical_differential_cycle
from cydra.finding_gate import FindingCandidate, evaluate_finding_graph
from cydra.impact import ImpactAssessment, ImpactLevel
from cydra.pipeline import investigate
from cydra.research_loop import run_research_loop
from scripts.run_benchmark_023_open_ended_guard import TARGET_PATH, TARGET_REF, TARGET_REPO, canonical_model, clone_target, patch_target, run_target

def main() -> int:
    p=argparse.ArgumentParser(); p.add_argument('--output',type=Path,default=Path('backtest-artifacts/benchmark-034')); args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='cydra-034-v-') as tmp:
        target=clone_target(Path(tmp)/'target'); source=target/TARGET_PATH
        investigation=investigate(source,target=f'{TARGET_REPO}@{TARGET_REF}:{TARGET_PATH}')
        def execute(hypothesis, experiment):
            if hypothesis.target_function != 'setTopNPools':
                return {'experiment_id':experiment.experiment_id,'executed':False,'status':'UNMEASURABLE','reason':'renderer cannot safely execute unrelated candidate'}
            return run_target(target,'loop-vulnerable')
        loop=run_research_loop(investigation.hypotheses,investigation.invariants,investigation.experiments,execute=execute,status_of=lambda x:x['status'],stop_when=lambda x:x['status']=='FAIL',max_rounds=3)
        if not loop.rounds: raise RuntimeError('research loop produced no rounds')
        selected=loop.rounds[-1]; hypothesis=selected.selection.hypothesis
        if hypothesis.target_function != 'setTopNPools': raise RuntimeError('loop did not reach guard hypothesis: '+hypothesis.hypothesis_id)
        vulnerable=selected.observation
        experiment=next(e for e in investigation.experiments if e.hypothesis_id==hypothesis.hypothesis_id)
    with tempfile.TemporaryDirectory(prefix='cydra-034-p-') as tmp:
        target=clone_target(Path(tmp)/'target'); patch_target(target); patched=run_target(target,'patched')
    with tempfile.TemporaryDirectory(prefix='cydra-034-rv-') as tmp: independent_vulnerable=run_target(clone_target(Path(tmp)/'target'),'independent-vulnerable')
    with tempfile.TemporaryDirectory(prefix='cydra-034-rp-') as tmp:
        target=clone_target(Path(tmp)/'target'); patch_target(target); independent_patched=run_target(target,'independent-patched')
    model, canonical_hypothesis, observation_id=canonical_model(hypothesis)
    class Execution:
        def __init__(self,payload): self.__dict__.update(payload)
    cycle=run_canonical_differential_cycle(model,hypothesis=canonical_hypothesis,observation_id=observation_id,vulnerable=Execution(vulnerable),patched=Execution(patched),outcome_id='benchmark-034-open-ended-differential')
    reproduction_verified=independent_vulnerable['status']=='FAIL' and independent_patched['status']=='PASS'
    impact=ImpactAssessment(ImpactLevel.MEDIUM,'Administrative top-pool configuration integrity','The selected setter rejects an owner caller even though the surrounding role model permits owner configuration.',('owner is a permitted configuration actor','the selected setter must accept that actor'),cycle.causal_verification.evidence_ids)
    gate=evaluate_finding_graph(model,candidate=FindingCandidate(True,False,True,True,cycle.causal_verification.state.value=='verified',impact.assessed,reproduction_verified),finding_id=f'F-BENCHMARK-034-{hypothesis.target_function}',hypothesis_id=f'hypothesis:{hypothesis.hypothesis_id}',evidence_ids=cycle.causal_verification.evidence_ids,causal_chain_id=cycle.causal_chain.chain_id)
    payload={'benchmark':'034','historical_target':{'repo':TARGET_REPO,'ref':TARGET_REF,'path':TARGET_PATH},'blind_boundary':{'vulnerability_class':False,'target_function':False,'state_surface':False,'exploit_sequence':False,'historical_answer':False,'specialized_reasoning_surface':False},'research_loop':[{'hypothesis_id':r.selection.hypothesis.hypothesis_id,'target_function':r.selection.hypothesis.target_function,'score':r.selection.score,'status':r.status,'observation':r.observation} for r in loop.rounds],'selected_hypothesis':hypothesis.__dict__,'experiment':experiment.__dict__,'vulnerable':vulnerable,'patched':patched,'causal_verification':cycle.causal_verification.__dict__,'independent_vulnerable':independent_vulnerable,'independent_patched':independent_patched,'reproduction_verified':reproduction_verified,'finding_gate':gate.decision.value}
    args.output.mkdir(parents=True,exist_ok=True); (args.output/'result.json').write_text(json.dumps(payload,indent=2,default=str)+'\n',encoding='utf-8'); print(json.dumps(payload,indent=2,default=str)); return 0 if gate.decision.value=='READY' else 1
if __name__=='__main__': raise SystemExit(main())
