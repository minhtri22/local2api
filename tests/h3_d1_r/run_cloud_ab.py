#!/usr/bin/env python3
"""H3.D1-R cloud A/B harness with corrected URL handling.

Research-only. Executes frozen RAW vs COMPILED prompts against one OpenAI-compatible
endpoint/model. API key is read only from an environment variable. It never writes secrets.
"""
from __future__ import annotations
import argparse, json, os, statistics, time, urllib.request, urllib.error
from pathlib import Path
from urllib.parse import urljoin, urlparse


def normalize_endpoint(base_url: str) -> str:
    """Normalize base URL to ensure correct chat/completions endpoint.
    
    Given base_url = https://integrate.api.nvidia.com/v1
    Returns: https://integrate.api.nvidia.com/v1/chat/completions
    
    NOT: https://integrate.api.nvidia.com/v1/v1/chat/completions
    """
    parsed = urlparse(base_url.rstrip("/"))
    # Reconstruct without any trailing path segments that might be /v1
    # The base_url should already be the API root (e.g., .../v1)
    # We append /chat/completions directly
    return parsed.scheme + "://" + parsed.netloc + parsed.path.rstrip("/") + "/chat/completions"


def post_json(url: str, payload: dict, api_key: str | None, timeout: int) -> tuple[dict, float]:
    data = json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json"}
    if api_key:
        headers["authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
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


def run_arm(base_url: str, model: str, api_key: str | None, arm_dir: Path, task_ids: list[str], max_tokens: int, temperature: float, top_p: float, timeout: int):
    rows = []
    endpoint = normalize_endpoint(base_url)
    for tid in task_ids:
        p = arm_dir / f"{tid}.json"
        payload = json.loads(p.read_text(encoding="utf-8"))
        payload["model"] = model
        payload.setdefault("temperature", temperature)
        payload.setdefault("top_p", top_p)
        payload.setdefault("max_tokens", max_tokens)
        payload.setdefault("stream", False)
        try:
            obj, wall_ms = post_json(endpoint, payload, api_key, timeout)
            rows.append({
                "id": tid,
                "status": "ok",
                "wall_ms": wall_ms,
                "usage": usage(obj),
                "text": text_from_response(obj),
                "raw_response": obj
            })
        except Exception as exc:
            rows.append({"id": tid, "status": "error", "error": repr(exc)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--api-key-env", default="NVIDIA_API_KEY")
    ap.add_argument("--evidence-dir", type=Path, default=Path("docs/result/evidence/h3_d1_r"))
    ap.add_argument("--max-tokens", type=int, default=1024)
    ap.add_argument("--temperature", type=float, default=0.2)
    ap.add_argument("--top-p", type=float, default=0.7)
    ap.add_argument("--timeout", type=int, default=300)
    args = ap.parse_args()

    # Self-test endpoint normalization
    test_url = normalize_endpoint(args.base_url)
    expected = args.base_url.rstrip("/") + "/chat/completions"
    assert test_url == expected, f"URL normalization failed: {test_url} != {expected}"
    print(f"Endpoint normalized to: {test_url}")

    key = os.getenv(args.api_key_env)
    if not key:
        raise SystemExit("H3_D1_R_BLOCKED_ROTATED_NVIDIA_API_KEY_NOT_SET")

    tasks = json.loads((args.evidence_dir / "corpora" / ".." / ".." / "h3_d1" / "frozen_tasks.json").read_text(encoding="utf-8"))["tasks"]
    ids = [t["id"] for t in tasks]

    print(f"Running RAW arm ({len(ids)} tasks)...")
    raw = run_arm(args.base_url, args.model, key, args.evidence_dir / "raw_payloads", ids, args.max_tokens, args.temperature, args.top_p, args.timeout)

    print(f"Running COMPILED arm ({len(ids)} tasks)...")
    comp = run_arm(args.base_url, args.model, key, args.evidence_dir / "compiled_payloads", ids, args.max_tokens, args.temperature, args.top_p, args.timeout)

    meta = {
        "model": args.model,
        "base_url": args.base_url,
        "normalized_endpoint": test_url,
        "api_key_env": args.api_key_env,
        "max_tokens": args.max_tokens,
        "temperature": args.temperature,
        "top_p": args.top_p,
        "task_ids": ids
    }
    (args.evidence_dir / "cloud_runs_raw.json").write_text(json.dumps({"meta": meta, "runs": raw}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (args.evidence_dir / "cloud_runs_compiled.json").write_text(json.dumps({"meta": meta, "runs": comp}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print("Cloud A/B execution complete. Manual/rubric scoring is still required before a verdict.")


if __name__ == "__main__":
    main()