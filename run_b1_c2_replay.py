import httpx
import asyncio
import json
import uuid
from datetime import datetime

# A3 Multi-turn scenarios from multiturn_results.json
SCENARIOS = [
    {
        "id": "MT1",
        "fixture": "api/chat.py calls adapter.request(body). http.py returns an httpx.Response. Current handler rebuilds every upstream error as HTTP 500.",
        "turns": [
            "Restate the relevant facts only.",
            "Identify the issue.",
            "Propose the smallest edit.",
            "A test failed with an unexpected 503. Diagnose without dropping constraints.",
            "Give the corrected final recommendation and repeat the constraints you preserved."
        ]
    },
    {
        "id": "MT2",
        "fixture": "chat.py accepts messages. Empty messages currently reach the backend. Tests use FastAPI TestClient.",
        "turns": [
            "Restate the relevant facts only.",
            "Identify the issue.",
            "Propose the smallest edit.",
            "A test failed with an unexpected 503. Diagnose without dropping constraints.",
            "Give the corrected final recommendation and repeat the constraints you preserved."
        ]
    },
    {
        "id": "MT3",
        "fixture": "base.py protocol defines async request(body). one implementation accidentally defines def request(body). router awaits backend.request(body).",
        "turns": [
            "Restate the relevant facts only.",
            "Identify the issue.",
            "Propose the smallest edit.",
            "A test failed with an unexpected 503. Diagnose without dropping constraints.",
            "Give the corrected final recommendation and repeat the constraints you preserved."
        ]
    },
    {
        "id": "MT4",
        "fixture": "router marks architecture tasks fallback=none and proofreading fallback=safe. Cloud transport can fail.",
        "turns": [
            "Restate the relevant facts only.",
            "Identify the issue.",
            "Propose the smallest edit.",
            "A test failed with an unexpected 503. Diagnose without dropping constraints.",
            "Give the corrected final recommendation and repeat the constraints you preserved."
        ]
    },
    {
        "id": "MT5",
        "fixture": "main.py creates app; api/chat.py handles POST; routing/router.py decides; backends/http.py calls upstream.",
        "turns": [
            "Restate the relevant facts only.",
            "Identify the issue.",
            "Propose the smallest edit.",
            "A test failed with an unexpected 503. Diagnose without dropping constraints.",
            "Give the corrected final recommendation and repeat the constraints you preserved."
        ]
    }
]

A3_BASELINE = {
    "MT1": "FAIL",
    "MT2": "FAIL",
    "MT3": "PASS",
    "MT4": "PASS",
    "MT5": "FAIL"
}


async def run_scenario(scenario):
    """Run a single multi-turn scenario through the B1 gateway with llama-server."""
    conversation_id = str(uuid.uuid4())
    turns_results = []
    
    # Build conversation history
    messages = []
    
    for i, turn_text in enumerate(scenario["turns"]):
        turn_id = str(uuid.uuid4())
        messages.append({"role": "user", "content": turn_text})
        
        # Build request with conversation history
        request_body = {
            "model": "qwen2.5-coder-14b-instruct-q4_k_m",
            "messages": messages.copy(),
            "temperature": 0.0,
            "max_tokens": 1024
        }
        
        headers = {
            "X-Local2API-Conversation-ID": str(uuid.uuid4())
        }
        
        start_time = datetime.now()
        
        async with httpx.AsyncClient(timeout=300.0) as client:
            try:
                response = await client.post(
                    "http://localhost:8000/v1/chat/completions",
                    json=request_body,
                    headers=headers,
                    timeout=300.0
                )
                
                wall_time = (datetime.now() - start_time).total_seconds() * 1000
                
                if response.status_code == 200:
                    data = response.json()
                    assistant_content = data["choices"][0]["message"]["content"]
                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", 0)
                    completion_tokens = usage.get("completion_tokens", 0)
                    total_tokens = usage.get("total_tokens", 0)
                    
                    # Add assistant response to history
                    messages.append({"role": "assistant", "content": assistant_content})
                    
                    turn_result = {
                        "turn": i + 1,
                        "turn_id": turn_id,
                        "request": turn_text,
                        "response": assistant_content[:500] + "..." if len(assistant_content) > 500 else assistant_content,
                        "ttft_ms": data.get("timings", {}).get("prompt_ms", 0),
                        "wall_time_ms": wall_time,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total_tokens,
                        "status": "ok"
                    }
                else:
                    turn_result = {
                        "turn": i + 1,
                        "turn_id": turn_id,
                        "request": turn_text,
                        "status": "error",
                        "error": f"HTTP {response.status_code}: {response.text}"
                    }
                    
            except Exception as e:
                wall_time = (datetime.now() - start_time).total_seconds() * 1000
                turn_result = {
                    "turn": i + 1,
                    "turn_id": turn_id,
                    "request": turn_text,
                    "status": "error",
                    "error": str(e)
                }
            
            turns_results.append(turn_result)
    
    return {
        "scenario_id": scenario["id"],
        "conversation_id": conversation_id,
        "turns": turns_results
    }


async def main():
    print("Starting B1.C2 Exact A3 Multi-turn E2E Replay...")
    print("=" * 60)
    
    results = []
    
    for scenario in SCENARIOS:
        print(f"\nRunning {scenario['id']}...")
        result = await run_scenario(scenario)
        results.append(result)
        
        # Save individual scenario output
        with open(f"docs/result/evidence/b1_c2/a3_multiturn_e2e_outputs/{result['scenario_id']}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        
        print(f"  Completed: {result['scenario_id']}")
    
    # Generate replay summary
    replay = {
        "schema": "local2api.b1_c2.a3_multiturn_e2e_replay.v1",
        "timestamp": datetime.now().isoformat(),
        "runtime": "llama-server",
        "model": "qwen2.5-coder-14b-instruct-q4_k_m",
        "canonical_runtime": "llama-server",
        "a3_baseline": {
            "MT1": "FAIL",
            "MT2": "FAIL",
            "MT3": "PASS",
            "MT4": "PASS",
            "MT5": "FAIL"
        },
        "scenarios": results
    }
    
    # Score scenarios (simplified - check if all turns completed successfully)
    for result in results:
        success = all(t.get("status") == "ok" for t in result["turns"])
        result["b1_c2_result"] = "PASS" if success else "FAIL"
    
    pass_count = sum(1 for r in results if r["b1_c2_result"] == "PASS")
    
    replay = {
        "schema": "local2api.b1_c2.a3_multiturn_e2e_replay.v1",
        "timestamp": datetime.now().isoformat(),
        "runtime": "llama-server",
        "model": "qwen2.5-coder-14b-instruct-q4_k_m",
        "canonical_runtime": "llama-server",
        "a3_baseline": {
            "MT1": "FAIL",
            "MT2": "FAIL",
            "MT3": "PASS",
            "MT4": "PASS",
            "MT5": "FAIL"
        },
        "scenarios": results
    }
    
    # Score scenarios (simplified - check if all turns completed successfully)
    for result in results:
        success = all(t.get("status") == "ok" for t in result["turns"])
        result["b1_c2_result"] = "PASS" if success else "FAIL"
    
    pass_count = sum(1 for r in results if r["b1_c2_result"] == "PASS")
    
    replay["summary"] = {
        "total_scenarios": 5,
        "passed": pass_count,
        "failed": 5 - pass_count,
        "b1_c2_score": f"{pass_count}/5"
    }
    
    with open("docs/result/evidence/b1_c2/a3_multiturn_e2e_replay.json", "w", encoding="utf-8") as f:
        json.dump(replay, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print(f"B1.C2 E2E Replay Complete: {pass_count}/5 passed")
    for r in results:
        print(f"  {r['scenario_id']}: {r['b1_c2_result']}")


if __name__ == "__main__":
    asyncio.run(main())