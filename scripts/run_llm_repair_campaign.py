from __future__ import annotations
import json, os, subprocess, time, urllib.request, urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
MODEL=os.getenv("CYDRA_LLM_MODEL","gpt-5.6-sol")
MAX_HOURS=float(os.getenv("CYDRA_EMERGENCY_MAX_HOURS","6"))
MAX_ATTEMPTS=int(os.getenv("CYDRA_LLM_MAX_ATTEMPTS","20"))
def run(cmd): return subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True,check=False)
def api(prompt):
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key:return None
    body={"model":MODEL,"instructions":"You are CYDRA's autonomous generic repair engineer. LLMs propose; deterministic tools test; evidence decides. Repair CYDRA only, never the target. No target-specific detectors, fake evidence, weakened fail-closed behavior, or bounty conclusions. Return JSON with decision PATCH or BOUNDARY, reason, patch, tests.","input":prompt,"max_output_tokens":14000}
    req=urllib.request.Request("https://api.openai.com/v1/responses",data=json.dumps(body).encode(),headers={"Authorization":"Bearer "+key,"Content-Type":"application/json"})
    try:
        with urllib.request.urlopen(req,timeout=300) as r:return json.loads(r.read().decode())
    except (urllib.error.URLError,urllib.error.HTTPError,TimeoutError) as e: print("LLM request failed:",e); return None
def output_text(r):
    if not r:return ""
    if isinstance(r.get("output_text"),str):return r["output_text"]
    return "\n".join(str(p.get("text","")) for x in r.get("output",[]) or [] for p in x.get("content",[]) or [] if p.get("type")=="output_text")
def files_for(cap):
    h=run(["rg","-l","--hidden","--glob","!.git",cap,"src","tests","scripts"])
    return list(dict.fromkeys(["AGENTS.md","PROJECT_BIBLE.md","src/cydra/capability_repair.py","scripts/run_live_contest.py"]+(h.stdout.splitlines() if h.returncode==0 else [])[:25]))
def context(artifact,cap):
    campaign=(artifact/"capability_campaign.json").read_text() if (artifact/"capability_campaign.json").exists() else "{}"
    out=["CAPABILITY: "+cap,"CAMPAIGN:\n"+campaign[:50000]]
    for p in files_for(cap):
        q=ROOT/p
        if q.is_file():out.append("\nFILE "+str(p)+"\n"+q.read_text(errors="replace")[:30000])
    return "\n".join(out)
def apply_patch(patch):
    if not patch.strip():return False,"empty patch"
    p=ROOT/".cydra-llm.patch";p.write_text(patch)
    try:
        c=run(["git","apply","--check","--whitespace=nowarn",str(p)])
        if c.returncode:return False,c.stderr[:8000]
        a=run(["git","apply","--whitespace=nowarn",str(p)])
        return a.returncode==0,(a.stderr or a.stdout)[:8000]
    finally:p.unlink(missing_ok=True)
def main():
    if not os.getenv("OPENAI_API_KEY"):print("OPENAI_API_KEY absent; LLM repair disabled.");return 0
    started=time.time()
    target=["python","scripts/run_live_contest.py","--target-spec","targets/live-contest.json","--target-checkout",".cydra-live-target","--output","live-artifacts"]
    for attempt in range(1,MAX_ATTEMPTS+1):
        if time.time()-started>=MAX_HOURS*3600:break
        print("=== autonomous repair/replay cycle",attempt,"===")
        result=run(target)
        artifact=ROOT/"live-artifacts"
        campaign=json.loads((artifact/"capability_campaign.json").read_text()) if (artifact/"capability_campaign.json").exists() else {}
        clusters=campaign.get("capability_clusters") or []
        if not clusters:print("No capability frontier remains.");return 0
        cap=str(clusters[0].get("capability") or "")
        if not cap:return 0
        response=api(context(artifact,cap)+"\n\nRunner output:\n"+result.stdout[-12000:]+result.stderr[-12000:])
        raw=output_text(response)
        try:proposal=json.loads(raw.strip())
        except Exception:print("Invalid LLM response:",raw[:4000]);return 3
        if proposal.get("decision")!="PATCH":print("LLM boundary:",proposal.get("reason",""));return 0
        ok,msg=apply_patch(str(proposal.get("patch") or ""));print("patch:",ok,msg)
        if not ok:continue
        tests=proposal.get("tests") or ["python","-m","pytest"]
        tr=run(tests if isinstance(tests,list) else ["python","-m","pytest"])
        if tr.returncode!=0:print("regression failed; retrying with failure context");continue
        print("regression passed; replaying exact frozen target.")
    print("Emergency autonomous repair ceiling reached.");return 0
if __name__=="__main__":raise SystemExit(main())
