from __future__ import annotations
import json, statistics, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from context_compile import compile_fixture, tokens

ROOT = Path(__file__).resolve().parents[2]
SKILL_TEXT = (ROOT / "skills/local-context-compiler/SKILL.md").read_text(encoding="utf-8")
SKILL_TOKENS = len(tokens(SKILL_TEXT))

def make_fixture(n: int):
    tag=f"{n:02d}"; entry=f"handle_retry_{tag}"; bridge=f"dispatch_retry_{tag}"; policy=f"select_policy_{tag}"; anchor=f"RETRY_POLICY_{tag}"; constraint=f"Do not modify auth_{tag}.py"
    blocks=[
      {"id":f"D{tag}-REQ","path":"REQUEST.md","kind":"request","content":f"Fix retry behavior for tenant {tag}; preserve compatibility."},
      {"id":f"D{tag}-CON","path":"CONSTRAINTS.md","kind":"constraint","content":constraint},
      {"id":f"D{tag}-ERR","path":f"logs/retry_{tag}.txt","kind":"error","content":f"AssertionError: {anchor} not applied on second retry"},
      {"id":f"D{tag}-TEST","path":f"tests/test_retry_{tag}.py","kind":"test","content":f"def test_retry_{tag}():\n    assert {entry}() == '{anchor}'"},
      {"id":f"D{tag}-A","path":f"src/tenant_{tag}/entry.py","kind":"code","content":f"from shared.bridge_{tag} import {bridge}\ndef {entry}():\n    return {bridge}()"},
      {"id":f"D{tag}-B","path":f"src/shared/bridge_{tag}.py","kind":"code","content":f"from policy.selector_{tag} import {policy}\ndef {bridge}():\n    return {policy}()"},
      {"id":f"D{tag}-C","path":f"src/policy/selector_{tag}.py","kind":"code","content":f"def {policy}():\n    return '{anchor}'"},
      {"id":f"D{tag}-CFG","path":f"config/runtime_{tag}.yaml","kind":"config","content":f"policy: {anchor}\nsecond_retry: enabled"},
    ]
    for j in range(10):
        blocks.append({"id":f"D{tag}-X{j}","path":f"src/noise/retry_helper_{tag}_{j}.py","kind":"code","content":(f"# retry tenant {tag} compatibility helper {j}\n"+"def helper(): return 'retry compatibility timeout'\n")*9})
    required={f"D{tag}-REQ",f"D{tag}-CON",f"D{tag}-ERR",f"D{tag}-TEST",f"D{tag}-A",f"D{tag}-B",f"D{tag}-C",f"D{tag}-CFG"}
    return {"id":f"D{tag}","task":f"Fix second retry for tenant {tag} while preserving compatibility.","hard_constraints":[constraint],"blocks":blocks,"required_ids":sorted(required)}

def evaluate():
    rows=[]
    for n in range(1,25):
        fx=make_fixture(n); raw_content="\n".join(b["content"] for b in fx["blocks"])
        raw=len(tokens(fx["task"]))+sum(len(tokens(c)) for c in fx["hard_constraints"])+len(tokens(raw_content)); skill_only=raw+SKILL_TOKENS
        ir=compile_fixture(fx); ids={e["id"] for e in ir["evidence"]}; req=set(fx["required_ids"]); recall=len(req&ids)/len(req); hard=all(c in ir["hard_constraints"] for c in fx["hard_constraints"]); skill_tool=ir["stats"]["compiled_tokens_proxy"]+SKILL_TOKENS
        rows.append({"id":fx["id"],"raw_tokens_proxy":raw,"skill_only_cloud_tokens_proxy":skill_only,"skill_tool_cloud_tokens_proxy":skill_tool,"skill_only_vs_raw_delta":skill_only/raw-1,"skill_tool_reduction_vs_raw":1-skill_tool/raw,"evidence_recall":recall,"hard_constraints_retained":hard})
    result={"schema":"local2api.h3_d0.skill_first_ab.v1","task_count":len(rows),"skill_tokens_proxy":SKILL_TOKENS,"pipelines":{"RAW":{"median_cloud_tokens_proxy":statistics.median(r["raw_tokens_proxy"] for r in rows)},"SKILL_ONLY":{"median_cloud_token_delta_vs_raw":statistics.median(r["skill_only_vs_raw_delta"] for r in rows),"note":"raw context must reach cloud before a cloud-only skill can select it"},"SKILL_PLUS_LOCAL_TOOL":{"median_cloud_input_reduction_vs_raw":statistics.median(r["skill_tool_reduction_vs_raw"] for r in rows),"mean_evidence_recall":statistics.mean(r["evidence_recall"] for r in rows),"min_evidence_recall":min(r["evidence_recall"] for r in rows),"hard_constraint_retention":sum(r["hard_constraints_retained"] for r in rows)/len(rows)}},"gates":{},"full_evidence_tasks":sum(r["evidence_recall"]==1 for r in rows),"limitations":["lexical token proxy, not provider billing tokenizer","synthetic fixtures","no downstream cloud model called","no real agent runtime integration","does not measure prompt-cache behavior or wall-clock latency"]}
    result["gates"]={"reduction_ge_30pct":result["pipelines"]["SKILL_PLUS_LOCAL_TOOL"]["median_cloud_input_reduction_vs_raw"]>=.30,"evidence_recall_ge_95pct":result["pipelines"]["SKILL_PLUS_LOCAL_TOOL"]["mean_evidence_recall"]>=.95,"hard_constraints_100pct":result["pipelines"]["SKILL_PLUS_LOCAL_TOOL"]["hard_constraint_retention"]==1.0}
    return result

if __name__=="__main__":
    out=evaluate(); p=ROOT/"docs/result/evidence/h3_d0/summary.json"; p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(out,indent=2)+"\n",encoding="utf-8"); print(json.dumps(out,indent=2)); assert all(out["gates"].values())
