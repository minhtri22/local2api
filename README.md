# local2api

`local2api` is a lightweight OpenAI-compatible inference gateway for a developer workstation. It routes suitable requests to a local LLM and can route heavier requests to an optional external backend, while keeping routing observable and avoiding unsafe silent degradation.

> Status: **v0.0.1 foundation**. Web-account/session adapters are intentionally not bundled into the core. Use only integrations that comply with the upstream provider's terms and your account permissions.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -e ".[test]"
python -m local2api.main
```

Default endpoint: `http://127.0.0.1:8000/v1/chat/completions`.

See `docs/index.md`, `plan.md`, and `docs/test_plan.md`.
