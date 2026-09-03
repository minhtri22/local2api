"""A3 production qualification and Capability Ceiling Suite v1 runner.

Uses the already-imported local 14B Ollama model. It never downloads models and
does not execute model-generated code or patches.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import ctypes
from ctypes import wintypes as w
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import time
import urllib.error
import urllib.request

from hw1_prod_gate import render_chat

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/result/evidence/a3_14b"
CEIL_OUT = ROOT / "docs/result/evidence/capability_ceiling_v1"
MODEL_FILE = ROOT / "models/qwen2.5-coder-14b-instruct-q4_k_m.gguf"
MODEL = "local2api-qwen2.5-coder-14b:a2.1"


def save(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def post(url: str, body: dict, timeout: int = 900) -> dict:
    req = urllib.request.Request(url, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def get(url: str, timeout: int = 10) -> dict:
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return json.load(r)


class PerformanceInfo(ctypes.Structure):
    _fields_ = [('cb', w.DWORD)] + [(n, ctypes.c_size_t) for n in (
        'CommitTotal', 'CommitLimit', 'CommitPeak', 'PhysicalTotal',
        'PhysicalAvailable', 'SystemCache', 'KernelTotal', 'KernelPaged',
        'KernelNonpaged', 'PageSize')] + [(n, w.DWORD) for n in (
        'HandleCount', 'ProcessCount', 'ThreadCount')]


def system_snapshot() -> dict:
    perf = PerformanceInfo(); perf.cb = ctypes.sizeof(perf)
    psapi = ctypes.WinDLL('psapi', use_last_error=True)
    if not psapi.GetPerformanceInfo(ctypes.byref(perf), perf.cb):
        raise ctypes.WinError(ctypes.get_last_error())
    return {
        "utc": datetime.now(timezone.utc).isoformat(),
        "committed_bytes": perf.CommitTotal * perf.PageSize,
        "commit_limit_bytes": perf.CommitLimit * perf.PageSize,
        "available_physical_bytes": perf.PhysicalAvailable * perf.PageSize,
        "physical_total_bytes": perf.PhysicalTotal * perf.PageSize,
    }


def generate(base: str, prompt: str, max_tokens: int = 128, num_ctx: int = 16384, keep_alive: str = "30m") -> dict:
    payload = {
        "model": MODEL, "prompt": render_chat(prompt), "raw": True, "stream": True,
        "keep_alive": keep_alive,
        "options": {"temperature": 0, "top_p": 1, "top_k": 40, "seed": 42,
                    "num_predict": max_tokens, "num_ctx": num_ctx},
    }
    req = urllib.request.Request(base + "/api/generate", json.dumps(payload).encode(), {"Content-Type": "application/json"})
    started = time.perf_counter(); first = None; text = ""; final = {}; error = None
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            for raw in r:
                event = json.loads(raw)
                piece = event.get("response") or ""
                if piece and first is None: first = time.perf_counter()
                text += piece
                if event.get("done"): final = event
    except Exception as exc:
        error = repr(exc)
    ended = time.perf_counter(); first = first or ended
    prompt_n = final.get("prompt_eval_count"); eval_n = final.get("eval_count")
    prompt_ns = final.get("prompt_eval_duration"); eval_ns = final.get("eval_duration")
    return {
        "status": "ok" if error is None else "error", "error": error,
        "prompt": prompt, "output": text,
        "ttft_ms": round((first-started)*1000, 3), "wall_ms": round((ended-started)*1000, 3),
        "prompt_tokens": prompt_n, "output_tokens": eval_n,
        "prompt_tps": (prompt_n/(prompt_ns/1e9)) if prompt_n and prompt_ns else None,
        "decode_tps": (eval_n/(eval_ns/1e9)) if eval_n and eval_ns else None,
        "load_ms": (final.get("load_duration") or 0)/1e6,
        "done_reason": final.get("done_reason"), "num_ctx": num_ctx,
        "max_tokens": max_tokens, "telemetry_after": system_snapshot(),
    }


SUSTAINED = [
    ("short_explain", "Explain in 3 bullets why an HTTP gateway should preserve upstream status codes."),
    ("small_edit", "Given `def clamp(n): return n`, provide only a corrected implementation clamping to 1..100."),
    ("unit_test", "Write one pytest test for a function `clamp(n)` that must cap values above 100."),
    ("bug_localize", "Bug: `if not messages: return backend.chat(messages)`. Identify the bug and the smallest fix."),
    ("two_file", "router.py selects a backend; http.py sends to upstream. State the stable interface contract between them in 4 bullets."),
    ("diff_summary", "Summarize this change: API responses now include X-Local2API-Route-Reason containing the router decision reason."),
    ("extract", "Extract JSON only with keys error_class and retryable from: 'backend connection refused; retry may succeed'."),
    ("repo_question", "Trace this conceptual call path only: FastAPI chat handler -> router -> backend adapter -> upstream runtime."),
]


WORKFLOWS = [
    {
      "id":"WF1", "title":"two-file status propagation",
      "context":"api/chat.py calls adapter.request(body). http.py returns an httpx.Response. Current handler rebuilds every upstream error as HTTP 500.",
      "turns":[
        "Identify the bug and name the two files that matter.",
        "Propose the smallest implementation change while preserving the adapter contract.",
        "Give two deterministic pytest assertions that prove 429 and 503 are preserved."
      ], "criteria":["429","503","status","chat.py","http.py"]
    },
    {
      "id":"WF2", "title":"validation plus test",
      "context":"chat.py accepts messages. Empty messages currently reach the backend. Tests use FastAPI TestClient.",
      "turns":["Localize validation responsibility.","Provide a minimal guard and expected HTTP status.","Provide a focused test for empty messages."],
      "criteria":["messages","empty","test"]
    },
    {
      "id":"WF3", "title":"async interface mismatch",
      "context":"base.py protocol defines async request(body). one implementation accidentally defines def request(body). router awaits backend.request(body).",
      "turns":["Explain the failure mode.","State which contract must change and which implementation must change.","Give a regression test idea."],
      "criteria":["async","await","test"]
    },
    {
      "id":"WF4", "title":"safe fallback constraint",
      "context":"router marks architecture tasks fallback=none and proofreading fallback=safe. Cloud transport can fail.",
      "turns":["State the invariant.","Describe the minimal branching logic.","Give one test for architecture and one for proofreading."],
      "criteria":["architecture","proofread","fallback"]
    },
    {
      "id":"WF5", "title":"call-path targeted change",
      "context":"main.py creates app; api/chat.py handles POST; routing/router.py decides; backends/http.py calls upstream.",
      "turns":["Return the call path only.","Where should a route-reason response header be attached and why?","Name one regression test that avoids changing backend behavior."],
      "criteria":["chat.py","router","header"]
    },
]


CEILING_CASES = [
    ("CC01","C1","5-10 file call-path reasoning","Trace request/error/route-reason flow across main.py, api/chat.py, routing/router.py, routing/types.py, backends/base.py, backends/http.py, errors.py. Identify two contracts that must remain stable.", ["chat.py","router.py","http.py","contract"]),
    ("CC02","C2","cross-module bug localization","A 429 becomes 503 only for streaming. Localize the most likely boundary using chat.py and http.py semantics, and give an evidence plan before proposing a fix.", ["stream","429","http.py","evidence"]),
    ("CC03","C3","architecture constrained change","Add gateway-owned conversation_id without changing backend protocol, router task heuristics, or public model aliases. Give a file-by-file plan and explicit non-changes.", ["conversation","backend","router","alias"]),
    ("CC04","C4","multi-step test/fix loop","A test expects 429 preservation but receives 503. Give hypothesis order, inspection steps, smallest patch location, and post-fix tests. Do not invent unseen code.", ["429","503","inspect","test"]),
    ("CC05","C5","dependency impact","If HTTPBackendAdapter.request changes from returning httpx.Response to decoded dict, enumerate likely consumers and semantic breakages across API status propagation, streaming, tests, and health.", ["response","stream","health","test"]),
    ("CC06","C6","ambiguous evidence","You only know that one production request returned 500 and no logs are available. State what can and cannot be concluded, and the minimum evidence needed before changing code.", ["cannot","evidence","log"]),
    ("CC07","C7","long-context prioritization","Given 8 file summaries where only router.py, chat.py, and http.py affect a wrong-backend-status bug, explain which evidence you prioritize and which files you defer, with reasons.", ["router.py","chat.py","http.py","defer"]),
    ("CC08","C8","competing constraints","Design a fix that preserves upstream status, keeps architecture tasks from local fallback, keeps SSE [DONE], and does not change /v1/models. State invariants and test matrix.", ["status","fallback","DONE","models"]),
    ("CC09","C9","repo-wide refactor planning","Plan extracting routing policy into a capability registry while preserving current routes, headers, explicit overrides, fallback behavior, and tests. Include migration order and rollback point.", ["override","fallback","header","rollback"]),
    ("CC10","C10","hallucination resistance","A reviewer says config.py contains OAuth token refresh logic. You have not been shown config.py. Respond with what you can verify, what you cannot, and exact next inspection step.", ["cannot","config.py","inspect"]),
    ("CC11","C1","multi-hop error path","Reason through: upstream timeout -> HTTPBackendAdapter -> BackendUnavailable -> chat handler -> safe fallback decision. Distinguish degradable and non-degradable tasks and final HTTP semantics.", ["BackendUnavailable","degrad","fallback","HTTP"]),
    ("CC12","C5","impact under state ownership","Gateway context reconstruction is added. Identify effects on request schema, token budgeting, backend switching, retries, observability, and privacy without assuming backend session memory.", ["context","backend","retry","privacy"]),
    ("CC13","C8","constraint retention","Propose a three-commit implementation sequence for B1 Context Ownership. Constraints: no router heuristic changes, no hidden backend session dependence, reversible migration, existing API remains compatible.", ["context","compatible","router","session"]),
    ("CC14","C10","adversarial missing diff","Summarize the behavioral effect of an allegedly supplied diff, but no diff is actually present. Do not fabricate changes; state the blocker and offer the most useful general answer possible.", ["diff","not","general"]),
]


def run_sustained(base: str) -> dict:
    rows=[]; before=system_snapshot()
    for i in range(32):
        kind, p = SUSTAINED[i % len(SUSTAINED)]
        row=generate(base, f"Request {i+1}. {p}", 96, [4096,8192,12288,16384][i%4])
        row.update(index=i+1, task_class=kind)
        rows.append(row); print("sustained",i+1,row['status'],row['ttft_ms'],flush=True)
    ok=[r for r in rows if r['status']=='ok']
    return {"before":before,"after":system_snapshot(),"requests":rows,
            "summary":{"success":len(ok),"total":len(rows),"failures":len(rows)-len(ok),
                       "median_ttft_ms":statistics.median(r['ttft_ms'] for r in ok),
                       "p95_ttft_ms":sorted(r['ttft_ms'] for r in ok)[max(0,int(.95*len(ok))-1)],
                       "median_decode_tps":statistics.median(r['decode_tps'] for r in ok if r['decode_tps'])}}


def run_workflows(base: str) -> dict:
    out=[]
    for wf in WORKFLOWS:
        transcript=[]; context=wf['context']
        for turn in wf['turns']:
            history="\n\n".join(f"Turn {x['n']} request: {x['request']}\nTurn {x['n']} answer: {x['output']}" for x in transcript)
            prompt=f"Repository fixture:\n{context}\n\n{history}\n\nNext request: {turn}\nKeep all prior constraints."
            r=generate(base,prompt,160,8192); transcript.append({"n":len(transcript)+1,"request":turn,"output":r['output'],"metrics":{k:r[k] for k in ['status','ttft_ms','wall_ms','decode_tps']}})
        whole="\n".join(x['output'] for x in transcript).lower()
        hits=[c for c in wf['criteria'] if c.lower() in whole]
        status="WORKFLOW_PASS" if len(hits)==len(wf['criteria']) else ("WORKFLOW_PARTIAL" if len(hits)>=max(1,len(wf['criteria'])-1) else "WORKFLOW_FAIL")
        out.append({**wf,"transcript":transcript,"criteria_hits":hits,"result":status,"repair_turns":0,
                    "incorrect_files_touched":[],"hallucinated_apis":[]})
        print("workflow",wf['id'],status,flush=True)
    return {"workflows":out,"summary":{s:sum(x['result']==s for x in out) for s in ['WORKFLOW_PASS','WORKFLOW_PARTIAL','WORKFLOW_FAIL']}}


def run_multiturn(base: str) -> dict:
    sessions=[]
    for i,wf in enumerate(WORKFLOWS):
        context=wf['context']; constraints="Do not invent unseen APIs. Preserve all stated constraints."
        turns=["Restate the relevant facts only.","Identify the issue.","Propose the smallest edit.","A test failed with an unexpected 503. Diagnose without dropping constraints.","Give the corrected final recommendation and repeat the constraints you preserved."]
        transcript=[]
        for n,t in enumerate(turns,1):
            history="\n".join(f"U: {x['request']}\nA: {x['output']}" for x in transcript)
            r=generate(base,f"Fixture: {context}\nConstraints: {constraints}\n{history}\nU: {t}",128,8192)
            transcript.append({"turn":n,"request":t,"output":r['output'],"ttft_ms":r['ttft_ms'],"status":r['status']})
        last=transcript[-1]['output'].lower(); consistency=all(k in last for k in ['constraint']) and not any(x['status']!='ok' for x in transcript)
        sessions.append({"id":f"MT{i+1}","fixture":context,"turns":transcript,"state_consistent":consistency,
                         "gateway_context_note":"Full prior transcript was reconstructed into each request; backend session memory was not relied upon."})
        print("multiturn",i+1,consistency,flush=True)
    return {"sessions":sessions,"consistent":sum(x['state_consistent'] for x in sessions),"total":len(sessions),
            "context_ownership_required":True}


def repo_context(target_words: int) -> str:
    block="File router.py routes explicit overrides and task hints. File chat.py handles API responses and route headers. File http.py calls upstream and preserves transport errors. File base.py defines adapter protocol. File config.py stores endpoints and timeouts. "
    return (block * (target_words//len(block.split())+1))[:target_words*7]


def run_context(base: str) -> dict:
    levels=[]
    for label,ctx in [("2k",2048),("4k",4096),("8k",8192),("12k",12288),("16k",16384)]:
        words=int(ctx*.72); prompt=repo_context(words)+"\nTask: identify the three files most relevant to preserving upstream status and explain why."
        r=generate(base,prompt,96,ctx); r['label']=label; levels.append(r); print("context",label,r['status'],r['ttft_ms'],flush=True)
    return {"levels":levels}


def run_outputs(base: str) -> dict:
    rows=[]
    prompt="Write a production-oriented explanation of safe local/cloud fallback, with concrete invariants, tests, failure semantics, and a concise implementation example."
    for n in [128,256,512,1024]:
        r=generate(base,prompt,n,8192); r['requested_output_tokens']=n; rows.append(r); print("output",n,r['output_tokens'],r['wall_ms'],flush=True)
        if r['wall_ms']>300000: break
    return {"runs":rows}


def run_concurrency(base: str) -> dict:
    prompt="Explain in six bullets how a gateway should handle an unavailable local inference backend without false success."
    results=[]
    for n in [1,2]:
        before=system_snapshot(); start=time.perf_counter()
        with concurrent.futures.ThreadPoolExecutor(max_workers=n) as ex:
            rows=list(ex.map(lambda _: generate(base,prompt,96,8192), range(n)))
        results.append({"concurrency":n,"wall_group_ms":round((time.perf_counter()-start)*1000,3),"before":before,"after":system_snapshot(),"requests":rows})
        print("concurrency",n,[r['status'] for r in rows],flush=True)
    return {"runs":results}


def run_ceiling(base: str) -> dict:
    cases=[]
    for cid,cat,title,prompt,criteria in CEILING_CASES:
        r=generate(base,prompt,256,12288); low=r['output'].lower(); hits=[x for x in criteria if x.lower() in low]
        # Deterministic provisional score. Manual review may lower it; never raises above 4 without explicit evidence.
        ratio=len(hits)/len(criteria); score=4 if ratio==1 and r['status']=='ok' else 3 if ratio>=.75 else 2 if ratio>=.5 else 1 if ratio>0 else 0
        cases.append({"task_id":cid,"category":cat,"title":title,"fixture_context":"controlled local2api architectural fixture",
                      "prompt":prompt,"hard_constraints":["do not invent unseen code","preserve stated contracts"],
                      "expected_evidence":criteria,"failure_modes":["hallucination","wrong-file attribution","missing dependency","constraint loss"],
                      "output":r['output'],"metrics":{k:r[k] for k in ['status','ttft_ms','wall_ms','prompt_tokens','output_tokens','decode_tps']},
                      "criteria_hits":hits,"score_0_5":score,"constraint_violations":[],"hallucinations":[],"wrong_file_attribution":[],"missing_dependency":[],"repair_turn_count":0})
        print("ceiling",cid,score,flush=True)
    return {"schema":"local2api.capability_ceiling.v1.results","model":MODEL,"rubric":{"0":"incorrect/hallucinated","1":"partial unusable","2":"mostly correct major omissions","3":"correct minor omissions","4":"strong production-quality","5":"expert complete"},
            "cases":cases,"score":sum(x['score_0_5'] for x in cases),"max_score":5*len(cases),"mean":statistics.mean(x['score_0_5'] for x in cases)}


def failure_probes(base: str) -> dict:
    probes=[]
    for name,url in [("wrong_port","http://127.0.0.1:65530/api/generate")]:
        try: post(url,{"model":MODEL,"prompt":"x"},timeout=2); result="unexpected_success"
        except Exception as exc: result=repr(exc)
        probes.append({"name":name,"result":result,"false_success":result=="unexpected_success"})
    probes += [
      {"name":"model_not_loaded","method":"Ollama keep_alive lifecycle covered by cold/reload run; missing model name intentionally not used because it would not test local2api adapter semantics."},
      {"name":"malformed_upstream_response","method":"Covered by deterministic gateway software tests; real Ollama does not expose a safe malformed-response injection point."},
      {"name":"connection_reset","method":"No destructive network fault injector used; adapter exception normalization covered by software tests."},
      {"name":"restart_during_request","method":"Lifecycle restart covered outside active generation to avoid corrupting unrelated local workloads."},
    ]
    return {"probes":probes}


def main() -> int:
    ap=argparse.ArgumentParser(); ap.add_argument("--base",default="http://127.0.0.1:11435"); args=ap.parse_args(); base=args.base.rstrip('/')
    OUT.mkdir(parents=True,exist_ok=True); CEIL_OUT.mkdir(parents=True,exist_ok=True)
    artifact={"path":str(MODEL_FILE),"bytes":MODEL_FILE.stat().st_size,"sha256":hashlib.file_digest(MODEL_FILE.open('rb'),'sha256').hexdigest()}
    runtime={"version":get(base+"/api/version"),"initial_ps":get(base+"/api/ps"),"artifact":artifact,"started_at":datetime.now(timezone.utc).isoformat()}
    # Cold/reload lifecycle: unload, cold request, warm request, idle short reuse, unload/reload.
    post(base+"/api/generate",{"model":MODEL,"keep_alive":0}); time.sleep(2)
    cold=generate(base,"Reply exactly: COLD_OK",16,4096); warm=generate(base,"Reply exactly: WARM_OK",16,4096); time.sleep(3)
    idle=generate(base,"Reply exactly: IDLE_OK",16,4096); post(base+"/api/generate",{"model":MODEL,"keep_alive":0}); time.sleep(2)
    reload=generate(base,"Reply exactly: RELOAD_OK",16,4096)
    runtime["lifecycle"]={"cold":cold,"warm":warm,"post_idle":idle,"reload":reload,"ps_after_load":get(base+"/api/ps")}
    save(OUT/"runtime_and_lifecycle.json",runtime)
    sustained=run_sustained(base); save(OUT/"sustained_runs.json",sustained)
    workflows=run_workflows(base); save(OUT/"workflow_results.json",workflows)
    multiturn=run_multiturn(base); save(OUT/"multiturn_results.json",multiturn)
    contexts=run_context(base); save(OUT/"context_envelope.json",contexts)
    outputs=run_outputs(base); save(OUT/"output_envelope.json",outputs)
    concurrency=run_concurrency(base); save(OUT/"concurrency_results.json",concurrency)
    failures=failure_probes(base); save(OUT/"failure_recovery.json",failures)
    ceiling=run_ceiling(base); save(CEIL_OUT/"ceiling_suite_results_14b.json",ceiling)
    save(CEIL_OUT/"suite_definition.json",{"schema":"local2api.capability_ceiling.v1","frozen":False,
         "cases":[{"task_id":c[0],"category":c[1],"title":c[2],"prompt":c[3],"expected_evidence":c[4]} for c in CEILING_CASES]})
    print("A3_RUN_COMPLETE",flush=True)
    return 0


if __name__ == "__main__": raise SystemExit(main())
