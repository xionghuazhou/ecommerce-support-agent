# Contributing to E-commerce Support Agent

Thanks for your interest! Issues and PRs are welcome.

## Development setup

Follow the [Quick Start](README.md#-quick-start) in the README (Python 3.11+, `pip install -r requirements.txt`, copy `.env.example` to `.env`, `python scripts/init_db.py`).

## Running checks

```bash
# Syntax check (same as CI)
python -m compileall -q backend

# End-to-end smoke test (with the server running)
cd backend && python scripts/test_api.py
```

## Guidelines

- **Open an issue first** for major changes so we can discuss the approach.
- Keep PRs focused — one feature or fix per PR.
- **Guardrails are sacred**: changes to `customer_agent.py` must keep the 5 reliability guardrails intact (order-number regex extraction, numeric consistency, fabrication interception, policy-question protection, no-key degradation). Add a smoke-test scenario for any new guardrail.
- New tools go in `backend/app/agents/tools/` and must be registered with a JSON schema in `prompts/`.
- Never commit `.env`, databases, or vector indexes — `.gitignore` covers them.

## Good first issues

Look for issues labeled `good first issue` — e.g. screenshots/GIF, pytest for guardrails, Dockerfile, English chat UI.