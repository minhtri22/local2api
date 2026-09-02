from __future__ import annotations

import argparse, json, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

from hw1_prod_gate import render_chat

CASES = [
    ("A01","LOCAL_SAFE","Explain why preserving upstream HTTP status matters.",["status"]),
    ("A02","LOCAL_SAFE","Explain a FastAPI request validation failure in two bullets.",["validation"]),
    ("A03","LOCAL_SAFE","What does a deterministic router buy us in testing?",["determin"]),
    ("A04","LOCAL_SAFE","Identify the bug: if not messages: return backend.chat(messages).",["empty","valid"]),
    ("A05","LOCAL_SAFE","Summarize safe fallback: cloud failure may fall back local only for degradable tasks.",["degrad","fallback"]),
    ("B01","LOCAL_SAFE","Write a Python helper that clamps n to 1..100.",["def ","min(","max("]),
    ("B02","LOCAL_SAFE","Add simple validation that messages is a non-empty list.",["list","messages"]),
    ("B03","LOCAL_ACCEPTABLE","Refactor a function with nested ifs using early returns; explain the change.",["return"]),
    ("B04","LOCAL_ACCEPTABLE","Show a small FastAPI endpoint returning {'ok': True}.",["FastAPI","ok"]),
    ("B05","LOCAL_ACCEPTABLE","Implement a helper selecting local when task_class == 'short'.",["local","short"]),
    ("C01","LOCAL_SAFE","Write one pytest assertion for HTTP 503.",["pytest","503"]),
    ("C02","LOCAL_SAFE","Name an edge case for an empty messages array.",["empty"]),
    ("C03","LOCAL_ACCEPTABLE","Write a pytest test idea for preserving an upstream 429.",["429"]),
    ("C04","LOCAL_ACCEPTABLE","What test proves SSE terminates with [DONE]?",["DONE"]),
    ("C05","LOCAL_ACCEPTABLE","Identify a missing test for explicit model override.",["override"]),
    ("D01","LOCAL_ACCEPTABLE","Across router.py and http.py, what interface contract should remain stable? Answer generally.",["backend"]),
    ("D02","LOCAL_ACCEPTABLE","Trace: API handler -> router -> backend -> upstream. Return the call path only.",["router","backend"]),
    ("D03","LOCAL_ACCEPTABLE","Summarize a diff that adds a route-reason response header.",["header","route"]),
    ("D04","LOCAL_ACCEPTABLE","Spot an interface mismatch: protocol expects async chat(), implementation defines sync chat().",["async","sync"]),
    ("D05","LOCAL_ACCEPTABLE","Why should backend switching not depend on hidden server session memory?",["state","context"]),
    ("E01","CLOUD_REQUIRED","Redesign the entire gateway architecture for multi-region HA with zero downtime.",["architecture"]),
    ("E02","CLOUD_REQUIRED","Perform a complex ten-file refactor with ambiguous requirements.",["clarif","require"]),
    ("E03","CLOUD_REQUIRED","Debug an intermittent distributed race without logs or reproduction.",["log","repro"]),
    ("E04","CLOUD_REQUIRED","Reason over a 200k-token repository and propose a migration plan.",["context","repository"]),
    ("E05","CLOUD_REQUIRED","Choose a security-critical auth redesign from incomplete evidence.",["security","evidence"]),
]

def call(url, model, prompt):
    req=urllib.request.Request(url.rstrip('/')+"/v1/completions", data=json.dumps({"model":model,"prompt":render_chat(prompt),"temperature":0,"top_p":1,"seed":42,"max_tokens":128}).encode(), headers={"Content-Type":"application/json"})
    t=time.perf_counter()
    with urllib.request.urlopen(req, timeout=900) as r: data=json.loads(r.read())
    return (data.get("choices") or [{}])[0].get("text",""), round((time.perf_counter()-t)*1000,3)

def main():
    p=argparse.ArgumentParser(); p.add_argument("--url",required=True); p.add_argument("--model",default="qwen2.5-coder:7b"); p.add_argument("--output",type=Path,required=True); a=p.parse_args()
    rows=[]
    for cid,cls,prompt,need in CASES:
        text,lat=call(a.url,a.model,prompt); low=text.lower(); passed=all(x.lower() in low for x in need)
        rows.append({"id":cid,"class":cls,"prompt":prompt,"criteria":{"contains_all":need},"latency_ms":lat,"pass":passed,"response":text})
        print(cid,cls,"PASS" if passed else "FAIL",lat)
    summary={}
    for cls in sorted({r["class"] for r in rows}):
        rs=[r for r in rows if r["class"]==cls]; summary[cls]={"passed":sum(r["pass"] for r in rs),"total":len(rs),"pass_rate":round(sum(r["pass"] for r in rs)/len(rs),3)}
    a.output.parent.mkdir(parents=True,exist_ok=True); a.output.write_text(json.dumps({"schema":"local2api.hw1.quality.v1","created_at":datetime.now(timezone.utc).isoformat(),"summary":summary,"cases":rows},indent=2),encoding="utf-8")
    print(summary); return 0

if __name__=="__main__": raise SystemExit(main())
