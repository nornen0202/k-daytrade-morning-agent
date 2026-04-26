# AGENTS.md

## Project structure

- `daytrade_agent/`: Python package and CLI
- `config/`: YAML configuration defaults and examples
- `prompts/`: LLM prompt templates
- `site_templates/`: Jinja templates and CSS for GitHub Pages
- `content/reports/`: public report artifacts
- `private_artifacts/`: ignored debug artifacts only
- `tests/`: fixture-backed tests

## Commands

```powershell
python -m pip install -e ".[dev]"
ruff check .
pytest
python -m daytrade_agent.cli run --dry-run --date 2026-04-27
python -m daytrade_agent.cli verify --date 2026-04-27
python -m daytrade_agent.cli build-site
```

## Security rules

- Never hardcode API keys, tokens, or personal identifiers.
- Never publish raw provider responses or debug prompts to `content/` or `dist/`.
- Store optional debug artifacts only under `private_artifacts/`.
- Do not add order execution, account lookup, or personal portfolio features.
- Scheduled Codex execution must use the self-hosted Windows runner app-server path,
  with `CODEX_BINARY`/`CODEX_HOME` coming from runner configuration or repository variables.

## Financial language rules

- The product is research support, not investment advice.
- Do not use project-prohibited promotional or manipulative phrasing.
- Use source IDs and data keys for material claims.
- If data is missing, stale, or unverified, write "데이터 부족".
- Avoid certainty when facts are incomplete.

## Public/private boundary

Public:

- `content/reports/YYYY-MM-DD/report.md`
- `content/reports/YYYY-MM-DD/summary.json`
- `content/reports/YYYY-MM-DD/verification.json`
- `dist/`

Private:

- `.env`
- `.cache/`
- `private_artifacts/`
- raw API responses
- debug logs

## Done when

- `pytest` passes.
- `ruff check .` passes.
- Dry-run report generation succeeds without API keys.
- Static site build creates latest and dated report pages.
- Verification status is visible on generated pages.
- Public artifacts contain no secrets or raw provider dumps.
