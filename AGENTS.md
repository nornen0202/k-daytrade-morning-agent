# AGENTS.md

## Project Purpose

This repository generates a daily Korean day-trading morning briefing report and publishes it as a static GitHub Pages site.

The system is for research support only. It must never place trades, send orders, guarantee returns, or provide direct investment advice.

## Core Commands

Install:

```bash
pip install -e ".[dev]"
```

Run dry report:

```bash
python -m daytrade_agent.cli run --dry-run --date 2026-04-27
```

Verify:

```bash
python -m daytrade_agent.cli verify --date 2026-04-27
```

Build site:

```bash
python -m daytrade_agent.cli build-site
```

Test:

```bash
ruff check .
pytest
```

## Repository Layout

- `daytrade_agent/collectors`: data collection
- `daytrade_agent/normalizers`: schemas and normalization
- `daytrade_agent/scoring`: deterministic candidate ranking
- `daytrade_agent/llm`: prompt construction, LLM report writing, verification
- `daytrade_agent/render`: static site rendering
- `content/reports`: public sanitized report content
- `private_artifacts`: private ignored raw/debug data
- `dist`: static site build output

## Security Rules

- Never commit `.env`.
- Never hardcode API keys.
- Never publish raw API responses to GitHub Pages.
- Never publish account identifiers or private holdings.
- Treat everything under `dist/` as public.
- Do not implement order placement.
- Do not call trading/order endpoints.
- Store optional debug artifacts only under `private_artifacts/`.
- Scheduled Codex execution should use the self-hosted Windows runner app-server path when `REPORT_LLM_PROVIDER=codex`, with `CODEX_BINARY` and `CODEX_HOME` coming from runner configuration or repository variables.

## Financial Language Rules

Forbidden expressions:

- 무조건 매수
- 확실한 수익
- 상한가 확정
- 작전주
- 세력주
- 조작

Use instead:

- 관찰 후보
- 조건부 시나리오
- 변동성 확대 가능성
- 단기 과열 위험
- 근거 부족 테마
- 가격 확인 필요

## Data Rules

- Do not invent prices, volume, news, disclosures, or source IDs.
- If price is missing, write "가격 확인 필요".
- If news or disclosure data is stale, mark it clearly.
- Every important claim should have `source_id` or `data_key`.
- LLM output must be verified before publication.
- If data is missing, stale, or unverified, write "데이터 부족" or a clearly equivalent data gap note.

## Public/Private Boundary

Public:

- `content/reports/YYYY-MM-DD/report.md`
- `content/reports/YYYY-MM-DD/summary.json`
- `content/reports/YYYY-MM-DD/verification.json`
- `dist/`

Private:

- `.env`
- `.cache/`
- `private_artifacts/`
- `.codex-report-workspace/`
- raw API responses
- debug logs

## Report Pipeline

1. Resolve report date and trading context.
2. Determine market open/closed status.
3. Collect category events: `political_theme`, `corporate_disclosure`, `global_issue`, `theme_surge`.
4. Normalize events into `MarketEvent` schema.
5. Resolve candidate symbols.
6. Enrich candidates with price snapshots.
7. Score candidates deterministically.
8. Build facts/candidates/sources bundle.
9. Generate Markdown report with LLM or deterministic fallback.
10. Verify report.
11. Save public report files under `content/reports/YYYY-MM-DD/`.
12. Build static site into `dist/`.
13. Deploy `dist/` to GitHub Pages.

## Done When

A change is complete only when:

- `ruff check .` passes.
- `pytest` passes.
- Dry-run report generation succeeds.
- Static site build succeeds.
- No secrets or raw data are present in `dist/`.
- README remains accurate.
- Verification status is visible on generated pages.
