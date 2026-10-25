# k-daytrade-morning-agent

`k-daytrade-morning-agent`는 한국 주식시장 장전 리서치 브리핑을 자동 생성하고
GitHub Pages에 정적 사이트로 배포하는 Python 프로젝트입니다. 출력물은 공개 데이터 기반의
의사결정 보조 자료이며 투자 조언이 아닙니다.

이 프로젝트는 매매 실행 기능을 포함하지 않습니다. 실제 거래 전에는 반드시 증권사 앱이나
공식 시세 화면에서 가격, 공시, 거래대금, 시간외 데이터를 다시 확인해야 합니다.

## 설치

Python 3.12 전용 가상환경을 먼저 만드세요. 다른 checkout의 editable 설치를 함께 쓰지 않습니다.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

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
- `NEWS_API_KEY`: NewsAPI.org 뉴스 조회
- `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`: Naver Search News API
- `ALPHA_VANTAGE_API_KEY`: Alpha Vantage 뉴스/시장 보조 데이터
- `QUOTE_PROVIDER_URL`: 호환 시세 provider endpoint
- `QUOTE_PROVIDER_API_KEY`: 선택 시세 provider bearer token
- `KIS_APP_KEY`, `KIS_APP_SECRET`: 향후 KIS quote adapter용
- `OPENAI_API_KEY`: LLM 기반 리포트 작성
- `OPENAI_REPORT_MODEL`: 선택, 기본값 `gpt-5.5`

GitHub Actions에서 Codex provider를 기본으로 쓰려면 repository variable을 아래처럼 둡니다.
Codex 실행 환경이 없으면 템플릿 작성기로 안전하게 fallback합니다.

- `REPORT_LLM_PROVIDER`: `codex`
- `CODEX_REPORT_MODEL`: `gpt-6.1-sol`

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
준비되어 있으면 `codex app-server` preflight 후 `gpt-6.1-sol` 모델로 리포트를 생성합니다. Codex
binary/login/model 접근이 불가능한 환경에서는 템플릿 작성기로 fallback해 배포를 계속합니다.

이 저장소는 현재 `REPORT_RUNS_ON=["self-hosted","Windows","X64","codex","k-daytrade"]`
변수로 전용 Windows runner를 선택합니다. `CODEX_BINARY`는 실제 실행 가능한 CLI 경로,
`CODEX_HOME`은 로그인 환경입니다. 특정 확장의 버전 경로는 업데이트 후 확인해야 합니다.
모델 접근은 preflight로 확인합니다. TradingAgents 인증·서비스·예약은 이 저장소가 관리하지 않습니다.

Codex 작성 모델의 기본 정본은 `config/data_sources.yml`의 `llm.default_codex_model`입니다.
`CODEX_REPORT_MODEL` 환경변수/repository variable은 명시적 override입니다.
2026-10-26 승인에 따라 이 저장소의 운영 override도 `gpt-6.1-sol`로 설정합니다.
`medium` effort와 요청 제한 180초를 유지합니다. API 결제 경로는 활성화하지 않습니다.
API용 `OPENAI_REPORT_MODEL` 및 선택 PR 리뷰 workflow는 이 Codex 로그인 경로와 별개입니다.
수동 `model_probe=true`는 실제 작성기를 한 번 호출하고 원고·상세 영수증을 private_artifacts에만
남깁니다. 이 모드에서는 리포트 커밋·Pages 배포를 하지 않으며 summary에 실제 모델·fallback·검증
상태만 표시합니다. Codex 자식 프로세스에는 수집 API 키나 OPENAI_API_KEY를 전달하지 않습니다.

Windows build는 일반 artifact로 `dist/`만 전달합니다. Ubuntu package job이
`download-artifact → configure-pages → upload-pages-artifact`를 수행하고 deploy job이 게시합니다.
Windows 서비스 PATH의 Git Bash에 의존하지 않습니다. 기존 cron은 유지합니다.
GitHub schedule은 지연될 수 있으며 08:45 도착을 보장하지 않습니다. 09:00 이후 생성된 기록은
장전 마감 준수로 집계하지 않습니다.
거래일 09:00 이후 실행되면 추가 수집·LLM 호출 없이 발행 지연 안내만 생성합니다.
이 상태는 새 연구 생성 성공으로 집계하지 않습니다.

수동 실행의 `rebuild_only=true`는 수집·원고·과거 기록을 변경하지 않고 사이트만 복구합니다.
실수집은 현재 KST 날짜만 허용합니다. 과거 날짜 테스트에는 `--dry-run`을 사용하세요.

검증 실패 시에도 Pages 배포는 계속됩니다. 이 경우 상세 페이지는 데이터 검증 실패 리포트를
표시하고 실패 이유를 공개합니다.

## 휴장일 설정

거래일은 `exchange-calendars`의 XKRX와 `config/holidays_kr.yml`의 검토된 변경일을 합칩니다.
2026년 지방선거·제헌절 변경을 반영했습니다. 예제 달력은 운영 근거로 사용하지 않습니다.
검토 범위 밖 연도는 `unknown`으로 처리하고 수집·후보 생성을 하지 않습니다.
연말 전에 KRX 공지와 대조하고 coverage_years를 갱신해야 합니다.
공식 KRX 페이지는 2026-10-25 직접 조회에서 403이었으므로 공식 실시간 달력 API로
표현하지 않습니다. 참고 공지 URL과 한계는 설정 파일에 기록돼 있습니다.
휴장일에는 외부 수집기를 호출하지 않고 `Market Closed Note`를 생성합니다.

## 데이터 소스

- OpenDART: 국내 공시
- RSS/Naver/NewsAPI/Alpha Vantage/yfinance provider: 정치/정책, 글로벌 이슈, 테마 변동 후보
- 호환 quote provider: 가격, 등락률, 거래량, 거래대금, 실제 시세 시각
- yfinance fallback: 지연 정규장 가격과 제공된 시세 시각. 거래대금은 미제공 시 누락 처리
- mock collector: API 키 없는 테스트와 dry-run

데이터가 없거나 오래되면 값을 만들지 않고 `insufficient` 상태와 "데이터 부족" 문구를 사용합니다.

뉴스 수집은 `NEWS_RSS_URLS`, Naver Search News, NewsAPI.org, Alpha Vantage, yfinance를
순서대로 시도하고 provider별 결과를 dedupe합니다. TradingAgents처럼 yfinance는 키 없이 쓰는
보조 provider로 남겨두고, 한국어 뉴스 적합성이 높은 Naver Search API와 NewsAPI.org를 우선
사용합니다. 시세는 `QUOTE_PROVIDER_URL`이 있으면 우선 사용하고, 없으면 yfinance quote fallback을
사용합니다.

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
저장 직전에도 실제 환경의 비밀값과 중첩 raw/token/account 필드를 검사해 공개 파일 생성을 거절합니다.
quote provider의 시장 문맥은 정해진 지표 스키마만 허용합니다.

수치와 단위가 인용된 이벤트/시세와 일치해야 합니다. 가격에는 스냅샷 ID와 기준 시각을
요구합니다. 미래·시각 불명·48시간 초과 뉴스는 순위에서 제외합니다. 지연 정규장 시세는
주말을 감안해 최대 96시간 이내만 참고하고 장전 예상체결로 표현하지 않습니다.
OpenDART list가 접수일만 주면 시각을 생성하지 않으며 공시를 순위에서 제외합니다.
LLM 원고 실패 시 같은 입력의 결정적 facts writer를 독립 검증하고 이것도 실패하면 공지만 게시합니다.
실패 공지에는 후보·점수를 싣지 않습니다. 사이트 빌드에서도 기존 통과 원고를 재검증합니다.
홈과 `status.json`은 마지막 생성, 마지막 검증 연구, 현재 유효 연구를 구별합니다.
날짜가 맞고 09:00 전일 때만 현재 후보를 표시하며 브라우저에서도 만료를 적용합니다.
fixture 리포트는 실시간 연구로 표시하지 않습니다.

## 운영 책임과 확인

정본 코드는 원격 main, 공개 기록은 `content/reports`, 배포 정본은 Pages artifact입니다.
로컬 checkout이나 Actions green만으로 품질·게시 성공을 판단하지 않습니다.
TradingAgents는 별도 연구·전략 실행 제품이고 이 프로젝트는 공개 장전 리서치입니다.
수집·LLM 비용은 독립 발생하며 예약을 자동 통합하지 않습니다.

유형별 이벤트 수, 근거 있는 후보 수, 마감 준수, writer fallback은 summary.metrics에 기록합니다.
고정 점수는 검증된 예측 모형이 아닙니다. 읽기 시간·실제 효용·LLM 호출 실비는 아직 미측정입니다.
비용 영수증 없이 비용을 0으로 주장하지 않습니다.
운영 담당은 본 저장소 유지보수자이며 전용 runner의 전원·인터넷·로그인 유지가 필요합니다.

실시간 소스의 수동 확인: `python scripts/verify_live_pipeline.py`.
예약을 추가하지 않고 결과를 `private_artifacts/live-pipeline-check`에만 저장합니다.
