# k-daytrade-morning-agent

`k-daytrade-morning-agent`는 한국 주식시장 장전 리서치 브리핑을 자동 생성하고
GitHub Pages에 정적 사이트로 배포하는 Python 프로젝트입니다. 출력물은 공개 데이터 기반의
의사결정 보조 자료이며 투자 조언이 아닙니다.

이 프로젝트는 매매 실행 기능을 포함하지 않습니다. 실제 거래 전에는 반드시 증권사 앱이나
공식 시세 화면에서 가격, 공시, 거래대금, 시간외 데이터를 다시 확인해야 합니다.

## 설치

```powershell
python -m pip install -e ".[dev]"
```

## 로컬 dry-run

API 키 없이 fixture/mock 데이터만 사용합니다.

```powershell
python -m daytrade_agent.cli run --dry-run --date 2026-04-27
python -m daytrade_agent.cli verify --date 2026-04-27
python -m daytrade_agent.cli build-site
```

생성되는 공개 파일:

- `content/reports/YYYY-MM-DD/report.md`
- `content/reports/YYYY-MM-DD/summary.json`
- `content/reports/YYYY-MM-DD/verification.json`
- `dist/`

비공개 디버그 파일은 `private_artifacts/`에만 저장되며 gitignore 대상입니다.

## GitHub Secrets

필요한 항목만 저장합니다. 값은 코드나 Markdown에 하드코딩하지 않습니다.

- `OPENDART_API_KEY`: OpenDART 공시 조회
- `NEWS_API_KEY`: 선택 뉴스 API
- `QUOTE_PROVIDER_URL`: 호환 시세 provider endpoint
- `QUOTE_PROVIDER_API_KEY`: 선택 시세 provider bearer token
- `KIS_APP_KEY`, `KIS_APP_SECRET`: 향후 KIS quote adapter용
- `OPENAI_API_KEY`: LLM 기반 리포트 작성
- `OPENAI_REPORT_MODEL`: 선택, 기본값 `gpt-5.5`

GitHub Actions에서 Codex provider를 기본으로 쓰려면 repository variable을 아래처럼 둡니다.
Codex 실행 환경이 없으면 템플릿 작성기로 안전하게 fallback합니다.

- `REPORT_LLM_PROVIDER`: `codex`
- `CODEX_REPORT_MODEL`: `gpt-5.5`

## GitHub Pages 설정

1. Repository Settings에서 Pages source를 GitHub Actions로 설정합니다.
2. 위 Secrets를 필요한 만큼 등록합니다.
3. `.github/workflows/daily-report.yml`가 `dist/`를 Pages artifact로 업로드하고 배포합니다.
4. Actions 권한은 repository Settings에서 "Read and write permissions"가 허용되어야 `content/reports` 커밋이 가능합니다.

Private repository에서 Pages가 막히는 플랜이면 GitHub API가 Pages 설정을 거부할 수 있습니다. 이 경우
저장소를 public으로 전환하거나 Pages를 지원하는 플랜/조직 정책을 먼저 적용해야 합니다.

## Daily workflow

GitHub Actions cron은 기본적으로 UTC입니다. KST 평일 08:45 실행을 위해 fallback cron은
`45 23 * * 0-4`입니다. 수동 실행은 `workflow_dispatch`로 지원하며 날짜 입력을 받을 수
있습니다.

`daily-report.yml`의 기본 리포트 생성 job은 `ubuntu-latest`에서 실행되어 self-hosted runner가
없어도 Pages 배포까지 진행됩니다. `REPORT_LLM_PROVIDER=codex`이고 runner에 Codex CLI와 로그인이
준비되어 있으면 `codex app-server` preflight 후 `gpt-5.5` 모델로 리포트를 생성합니다. Codex
binary/login/model 접근이 불가능한 환경에서는 템플릿 작성기로 fallback해 배포를 계속합니다.

검증 실패 시에도 Pages 배포는 계속됩니다. 이 경우 상세 페이지는 데이터 검증 실패 리포트를
표시하고 실패 이유를 공개합니다.

## 휴장일 설정

주말은 자동으로 휴장 처리합니다. 한국 거래소 휴장일은 `config/holidays_kr.example.yml`을
`config/holidays_kr.yml`로 복사한 뒤 운영 연도에 맞게 갱신하세요. 휴장일에는 외부 수집기를
호출하지 않고 `Market Closed Note`를 생성합니다.

## 데이터 소스

- OpenDART: 국내 공시
- RSS/news provider: 정치/정책, 글로벌 이슈, 테마 변동 후보
- 호환 quote provider: 현재가, 등락률, 거래량, 거래대금, 시각
- mock collector: API 키 없는 테스트와 dry-run

데이터가 없거나 오래되면 값을 만들지 않고 `insufficient` 상태와 "데이터 부족" 문구를 사용합니다.

## 테스트

```powershell
ruff check .
pytest
python -m daytrade_agent.cli run --dry-run --date 2026-04-27
python -m daytrade_agent.cli build-site
```

## 검증 정책

검증기는 프로젝트 금지 문구, 출처 없는 수치, 가격 스냅샷 없는 가격 표현, 후보 목록에 없는
종목코드, 투자권유성 표현, 데이터 부족 상태에서의 확정 표현을 검사합니다. 공개 사이트에는 raw
provider 응답, secret, 개인 자산 정보, 포트폴리오 비중을 포함하지 않습니다.
