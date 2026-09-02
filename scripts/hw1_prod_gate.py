from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SYSTEM = "You are Qwen, created by Alibaba Cloud. You are a helpful assistant."


def render_chat(user: str, system: str = SYSTEM) -> str:
    return f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{user}<|im_end|>\n<|im_start|>assistant\n"


def post_json(url: str, payload: dict[str, Any], timeout: int = 900) -> dict[str, Any]:
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def tokenize(llama_url: str, prompt: str) -> list[int]:
    result = post_json(f"{llama_url.rstrip('/')}/tokenize", {"content": prompt, "add_special": False, "parse_special": True})
    return [int(x) for x in result.get("tokens", [])]


def completion(provider: str, base_url: str, model: str, prompt: str, max_tokens: int, seed: int) -> dict[str, Any]:
    if provider == "ollama":
        payload = {
            "model": model, "prompt": prompt, "raw": True, "stream": True,
            "options": {"temperature": 0, "top_p": 1, "seed": seed, "num_predict": max_tokens, "num_ctx": 16384},
            "keep_alive": "30m",
        }
        endpoint = f"{base_url.rstrip('/')}/api/generate"
    else:
        payload = {
            "prompt": prompt, "stream": True, "temperature": 0, "top_p": 1,
            "seed": seed, "n_predict": max_tokens, "cache_prompt": False,
        }
        endpoint = f"{base_url.rstrip('/')}/completion"
    req = urllib.request.Request(endpoint, data=json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
    started = time.perf_counter(); first = None; text = ""; final: dict[str, Any] = {}; usage: dict[str, Any] = {}
    try:
        with urllib.request.urlopen(req, timeout=900) as r:
            for raw in r:
                line = raw.decode('utf-8').strip()
                if provider == "ollama":
                    if not line: continue
                    event = json.loads(line)
                    piece = event.get('response') or ''
                    if event.get('done'): final = event
                else:
                    if not line.startswith('data:'): continue
                    data = line[5:].strip()
                    if data == '[DONE]': break
                    event = json.loads(data); final = event
                    piece = event.get('content') or ''
                if piece and first is None: first = time.perf_counter()
                text += piece; usage = event.get('usage') or usage
    except urllib.error.HTTPError as exc:
        return {"error": f"HTTP {exc.code}: {exc.read().decode('utf-8','replace')}", "wall_ms": round((time.perf_counter()-started)*1000,3)}
    ended = time.perf_counter(); first = first or ended
    timings = final.get("timings", {})
    if provider == "ollama":
        prompt_n = final.get("prompt_eval_count")
        predicted_n = final.get("eval_count")
        prompt_ns = final.get("prompt_eval_duration")
        predicted_ns = final.get("eval_duration")
        prompt_rate = (prompt_n / (prompt_ns / 1e9)) if prompt_n and prompt_ns else None
        predicted_rate = (predicted_n / (predicted_ns / 1e9)) if predicted_n and predicted_ns else None
    else:
        prompt_n = timings.get("prompt_n")
        predicted_n = timings.get("predicted_n")
        prompt_rate = timings.get("prompt_per_second")
        predicted_rate = timings.get("predicted_per_second")
    return {
        "wall_ms": round((ended - started) * 1000, 3),
        "ttft_ms": round((first - started) * 1000, 3),
        "prompt_tokens": usage.get("prompt_tokens") or prompt_n,
        "completion_tokens": usage.get("completion_tokens") or predicted_n,
        "prompt_tokens_per_s": prompt_rate,
        "generation_tokens_per_s": predicted_rate,
        "text": text,
        "raw_timings": timings,
    }


def deterministic_context(lines_count: int) -> str:
    lines = []
    i = 0
    while i < lines_count:
        lines.append(
            f"def handler_{i}(request, router):\n"
            f"    # deterministic repository fixture {i}: validate request, select backend, preserve errors\n"
            f"    if not request.messages: raise ValueError('messages required')\n"
            f"    decision = router.route(request)\n"
            f"    return decision.backend.chat(request)\n"
        )
        i += 1
    return "\n".join(lines)


def calibrated_prompt(llama_url: str, target_tokens: int) -> tuple[str, list[int]]:
    lo, hi = 1, max(10, target_tokens // 10)
    while True:
        p = render_chat(deterministic_context(hi) + "\n\nTask: identify three concrete reliability risks and propose one-line fixes.")
        if len(tokenize(llama_url, p)) >= target_tokens: break
        hi *= 2
    best = p; best_tokens = tokenize(llama_url, p)
    while lo <= hi:
        mid=(lo+hi)//2
        p=render_chat(deterministic_context(mid)+"\n\nTask: identify three concrete reliability risks and propose one-line fixes.")
        toks=tokenize(llama_url,p)
        if len(toks) <= target_tokens:
            best, best_tokens = p, toks; lo=mid+1
        else: hi=mid-1
    return best, best_tokens


def summarize(samples: list[dict[str, Any]]) -> dict[str, Any]:
    def med(key: str):
        vals = [float(s[key]) for s in samples if s.get(key) is not None]
        return round(statistics.median(vals), 3) if vals else None
    return {"runs": len(samples), "failures": sum(1 for s in samples if s.get('error')), "median_ttft_ms": med("ttft_ms"), "median_wall_ms": med("wall_ms"), "median_prompt_tokens_per_s": med("prompt_tokens_per_s"), "median_generation_tokens_per_s": med("generation_tokens_per_s")}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["parity", "fixture", "scale"], required=True)
    p.add_argument("--provider", choices=["ollama", "llama_server"], default=None)
    p.add_argument("--fixture", type=Path)
    p.add_argument("--levels", nargs="+", choices=["1k", "4k", "8k", "16k"])
    p.add_argument("--ollama-url", default="http://127.0.0.1:11435")
    p.add_argument("--llama-url", default="http://127.0.0.1:11437")
    p.add_argument("--model", default="qwen2.5-coder:7b")
    p.add_argument("--gguf", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    base = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model": args.model,
        "gguf": str(args.gguf),
        "gguf_sha256": sha256(args.gguf),
        "generation": {"temperature": 0, "top_p": 1, "seed": 42, "max_tokens": 64, "context_size": 16384},
    }
    if args.mode == "parity":
        user = "Explain in five concise bullets how a capability-aware local/cloud router should preserve safe fallback semantics."
        prompt = render_chat(user)
        toks = tokenize(args.llama_url, prompt)
        runs = {}
        for name, url in (("ollama", args.ollama_url), ("llama_server", args.llama_url)):
            runs[name] = completion(name, url, args.model, prompt, 64, 42)
        base.update({"schema": "local2api.hw1.parity.v1", "raw_messages": {"system": SYSTEM, "user": user}, "rendered_prompt": prompt, "rendered_prompt_utf8_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "token_count": len(toks), "token_ids": toks, "runtime_results": runs})
    elif args.mode == "fixture":
        levels = {"1k": 900, "4k": 3600, "8k": 7200, "16k": 14500}
        fixtures = {}
        for label, target_tokens in levels.items():
            prompt, toks = calibrated_prompt(args.llama_url, target_tokens)
            fixtures[label] = {
                "target_tokens": target_tokens,
                "token_count": len(toks),
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                "token_ids": toks,
                "rendered_prompt": prompt,
            }
        base.update({"schema": "local2api.hw1.context_fixture.v1", "levels": fixtures})
    else:
        if not args.provider or not args.fixture:
            p.error("--mode scale requires --provider and --fixture")
        fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
        results = {}
        url = args.ollama_url if args.provider == "ollama" else args.llama_url
        selected = set(args.levels or fixture["levels"].keys())
        for label, item in fixture["levels"].items():
            if label not in selected:
                continue
            prompt = item["rendered_prompt"]
            completion(args.provider, url, args.model, prompt, 16, 42)
            samples = [completion(args.provider, url, args.model, prompt, 64, 42) for _ in range(3)]
            results[label] = {
                "token_count": item["token_count"],
                "prompt_sha256": item["prompt_sha256"],
                "samples": samples,
                "summary": summarize(samples),
            }
            base.update({"schema": "local2api.hw1.context_scale_runtime.v1", "provider": args.provider, "levels": results})
            args.output.write_text(json.dumps(base, indent=2), encoding="utf-8")
        base.update({"schema": "local2api.hw1.context_scale_runtime.v1", "provider": args.provider, "levels": results})
    args.output.write_text(json.dumps(base, indent=2), encoding="utf-8")
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
