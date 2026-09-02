from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Sample:
    provider: str
    model: str
    run: int
    ttft_ms: float
    wall_ms: float
    load_ms: float
    prompt_tokens: int
    prompt_tokens_per_s: float | None
    generated_tokens: int
    generation_tokens_per_s: float | None


def ns_to_ms(value: int | None) -> float:
    return round((value or 0) / 1_000_000, 3)


def rate(count: int | None, duration_ns: int | None) -> float | None:
    if not count or not duration_ns:
        return None
    return round(count / (duration_ns / 1_000_000_000), 3)


def stream_chat(base_url: str, model: str, prompt: str, num_predict: int) -> tuple[Sample, dict[str, Any]]:
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "options": {"temperature": 0, "num_predict": num_predict},
            "keep_alive": "10m",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/chat",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()
    first_token_at: float | None = None
    final: dict[str, Any] = {}
    with urllib.request.urlopen(request, timeout=900) as response:
        for raw_line in response:
            if not raw_line.strip():
                continue
            event = json.loads(raw_line)
            content = event.get("message", {}).get("content", "")
            if content and first_token_at is None:
                first_token_at = time.perf_counter()
            if event.get("done"):
                final = event
    ended = time.perf_counter()

    if first_token_at is None:
        first_token_at = ended

    sample = Sample(
        provider="ollama",
        model=model,
        run=0,
        ttft_ms=round((first_token_at - started) * 1000, 3),
        wall_ms=round((ended - started) * 1000, 3),
        load_ms=ns_to_ms(final.get("load_duration")),
        prompt_tokens=int(final.get("prompt_eval_count", 0)),
        prompt_tokens_per_s=rate(final.get("prompt_eval_count"), final.get("prompt_eval_duration")),
        generated_tokens=int(final.get("eval_count", 0)),
        generation_tokens_per_s=rate(final.get("eval_count"), final.get("eval_duration")),
    )
    return sample, final


def stream_openai_chat(
    base_url: str, model: str, prompt: str, num_predict: int
) -> tuple[Sample, dict[str, Any]]:
    payload = json.dumps(
        {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
            "temperature": 0,
            "max_tokens": num_predict,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()
    first_token_at: float | None = None
    generated_text = ""
    final: dict[str, Any] = {}
    with urllib.request.urlopen(request, timeout=900) as response:
        for raw_line in response:
            line = raw_line.decode("utf-8").strip()
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            event = json.loads(data)
            delta = event.get("choices", [{}])[0].get("delta", {}).get("content") or ""
            if delta:
                generated_text += delta
                if first_token_at is None:
                    first_token_at = time.perf_counter()
            timings = event.get("timings")
            if timings:
                final = timings
    ended = time.perf_counter()

    if first_token_at is None:
        first_token_at = ended

    prompt_tokens = int(final.get("prompt_n", 0) or 0)
    generated_tokens = int(final.get("predicted_n", 0) or 0)
    prompt_rate = final.get("prompt_per_second")
    gen_rate = final.get("predicted_per_second")
    sample = Sample(
        provider="openai",
        model=model,
        run=0,
        ttft_ms=round((first_token_at - started) * 1000, 3),
        wall_ms=round((ended - started) * 1000, 3),
        load_ms=0.0,
        prompt_tokens=prompt_tokens,
        prompt_tokens_per_s=round(float(prompt_rate), 3) if prompt_rate else None,
        generated_tokens=generated_tokens,
        generation_tokens_per_s=round(float(gen_rate), 3) if gen_rate else None,
    )
    final = {"timings": final, "generated_text_chars": len(generated_text)}
    return sample, final


def median(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return round(statistics.median(present), 3) if present else None


def main() -> int:
    parser = argparse.ArgumentParser(description="HW1 benchmark against Ollama or an OpenAI-compatible server")
    parser.add_argument("--provider", choices=("ollama", "openai"), default="ollama")
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--num-predict", type=int, default=128)
    parser.add_argument("--base-url", default="http://127.0.0.1:11434")
    parser.add_argument(
        "--prompt",
        default=(
            "You are reviewing a Python FastAPI repository. Give exactly five concise bullets "
            "describing how to implement a capability-aware local/cloud router with safe fallback."
        ),
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    samples: list[Sample] = []
    raw_finals: list[dict[str, Any]] = []
    for model in args.models:
        for run_index in range(1, args.runs + 1):
            if args.provider == "ollama":
                sample, final = stream_chat(args.base_url, model, args.prompt, args.num_predict)
            else:
                sample, final = stream_openai_chat(args.base_url, model, args.prompt, args.num_predict)
            sample.run = run_index
            samples.append(sample)
            raw_finals.append({"model": model, "run": run_index, "final": final})
            print(
                f"{model} run={run_index} ttft={sample.ttft_ms:.1f}ms "
                f"prompt={sample.prompt_tokens_per_s} tok/s gen={sample.generation_tokens_per_s} tok/s"
            )

    summaries: dict[str, dict[str, Any]] = {}
    for model in args.models:
        model_samples = [sample for sample in samples if sample.model == model]
        summaries[model] = {
            "runs": len(model_samples),
            "median_ttft_ms": median([sample.ttft_ms for sample in model_samples]),
            "median_wall_ms": median([sample.wall_ms for sample in model_samples]),
            "median_load_ms": median([sample.load_ms for sample in model_samples]),
            "median_prompt_tokens_per_s": median([sample.prompt_tokens_per_s for sample in model_samples]),
            "median_generation_tokens_per_s": median(
                [sample.generation_tokens_per_s for sample in model_samples]
            ),
        }

    result = {
        "schema": f"local2api.hw1.{args.provider}.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
        "config": {
            "provider": args.provider,
            "base_url": args.base_url,
            "models": args.models,
            "runs": args.runs,
            "num_predict": args.num_predict,
            "prompt": args.prompt,
        },
        "summary": summaries,
        "samples": [asdict(sample) for sample in samples],
        "raw_final_events": raw_finals,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
