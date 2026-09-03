#!/usr/bin/env python3
"""H3.D1 cloud A/B harness.

Research-only. Executes frozen RAW vs COMPILED prompts against one OpenAI-compatible
endpoint/model. API key is read only from an environment variable. It never writes secrets.
"""
from __future__ import annotations
import argparse, json, os, statistics, time, urllib.request, urllib.error
from pathlib import Path


def post_json(url: str, payload: dict, api_key: str | None, timeout: int) -> tuple[dict, float]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url.rstrip("/") + "/v1/chat/completions", data=data, headers=headers, method="POST")
    started = time.perf_counter()
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    wall_ms = (time.perf_counter() - started) * 1000
    return json.loads(raw.decode("utf-8")), wall_ms


def text_from_response(obj: dict) -> str:
    try:
        return obj["choices"][0]["message"]["content"] or ""
    except Exception:
        return ""


def usage(obj: dict) -> dict:
    u = obj.get("usage") or {}
    return {
        "prompt_tokens": u.get("prompt_tokens"),
        "completion_tokens": u.get("completion_tokens"),
        "total_tokens": u.get("total_tokens"),
        "prompt_tokens_details": u.get("prompt_tokens_details"),
    }


def run_arm(base_url: str, model: str, api_key: str | None, arm_dir: Path, task_ids: list[str], max_tokens: int, timeout: int):
    rows = []
    for tid in task_ids:
        p = arm_dir / f"{tid}.json"
        payload = json.loads(p.read_text(encoding="utf-8"))
        payload["model"] = model
        payload.setdefault("temperature", 0)
        payload.setdefault("max_tokens", max_tokens)
        try:
            obj, wall_ms = post_json(base_url, payload, api_key, timeout)
            rows.append({"id": tid, "status": "ok", "wall_ms": wall_ms, "usage": usage(obj), "text": text_from_response(obj), "raw_response": obj})
        except Exception as exc:
            rows.append({"id": tid, "status": "error", "error": repr(exc)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key-env", default="H3_D1_API_KEY")
    ap.add_argument("--evidence-dir", type=Path, default=Path("docs/result/evidence/h3_d1"))
    ap.add_argument("--max-tokens", type=int, default=700)
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()
    key = os.getenv(args.api_key_env)
    tasks = json.loads((args.evidence_dir / "frozen_tasks.json").read_text(encoding="utf-8"))["tasks"]
    ids = [t["id"] for t in tasks]
    raw = run_arm(args.base_url, args.model, key, args.evidence_dir / "raw_payloads", ids, args.max_tokens, args.timeout)
    comp = run_arm(args.base_url, args.model, key, args.evidence_dir / "compiled_payloads", ids, args.max_tokens, args.timeout)
    meta = {"model": args.model, "base_url": args.base_url, "api_key_env": args.api_key_env, "max_tokens": args.max_tokens, "task_ids": ids}
    (args.evidence_dir / "cloud_runs_raw.json").write_text(json.dumps({"meta":meta,"runs":raw},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    (args.evidence_dir / "cloud_runs_compiled.json").write_text(json.dumps({"meta":meta,"runs":comp},indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print("Cloud A/B execution complete. Manual/rubric scoring is still required before a verdict.")

if __name__ == "__main__":
    main()
