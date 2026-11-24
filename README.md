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

API 키 없이 합성 fixture를 사용합니다. 기존 운영 기록과 구분된 경로를 지정하세요.

```powershell
$env:DAYTRADE_CONTENT_DIR = '.runtime/dry-run/reports'
$env:DAYTRADE_DIST_DIR = '.runtime/dry-run/dist'
python -m daytrade_agent.cli run --dry-run --date 2026-11-20 --fixture standard
python -m daytrade_agent.cli verify --date 2026-11-20
python -m daytrade_agent.cli build-site
```

생성되는 공개 파일:

- `content/reports/YYYY-MM-DD/report.md`
- `content/reports/YYYY-MM-DD/summary.json`
- `content/reports/YYYY-MM-DD/verification.json`
- `dist/`

비공개 디버그 파일은 `private_artifacts/`에만 저장되며 gitignore 대상입니다.
`--fixture`는 `standard`(기본), `no-quotes`, `mixed-timestamps`, `stale`을 지원합니다.
데이터 시각은 선택한 거래일 08:45 KST를 기준으로 이동합니다. 휴장·미검토일에는 안내만 생성합니다.
dry-run은 기존 실수집 보고서를 덮어쓰지 않습니다. 같은 경로에서 다음 사례를 실행하면 해당 fixture 날짜가 갱신됩니다.

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
3. `.github/workflows/morning-report.yml`가 선택된 커밋의 `dist/`를 Pages 아티팩트로 업로드하고 배포합니다.
4. Actions 권한은 repository Settings에서 "Read and write permissions"가 허용되어야 `content/reports` 커밋이 가능합니다.

Private repository에서 Pages가 막히는 플랜이면 GitHub API가 Pages 설정을 거부할 수 있습니다. 이 경우
저장소를 public으로 전환하거나 Pages를 지원하는 플랜/조직 정책을 먼저 적용해야 합니다.

## Daily workflow

Windows 작업 스케줄러가 평일 08:45 Asia/Seoul에 전용 체크아웃에서 수집을 직접 시작합니다.
09:00과 09:05에는 장전 결과가 없는 경우 지연 안내를 선택하거나 앞선 Git 푸시를 복구합니다.
기존 GitHub cron `45 23 * * 0-4`는 보조 수집 경로입니다. 두 시작 경로는 동일한 XKRX
거래일 판정과 수집·검증 코드로 진입합니다. 주말에는 건너뛰고 평일 휴장에는 수집 없이 안내를 생성합니다.

GitHub 보조 수집 job의 기본 runner는 `ubuntu-latest`입니다. `REPORT_LLM_PROVIDER=codex`이고
Codex CLI, 로그인, 모델 접근이 준비되어 있으면 작성기가 `codex app-server`를 사용합니다.
작성 환경이 없으면 템플릿 작성기로 전환합니다.

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

수집 결과는 각 실행 경로의 `private_artifacts/morning/`에 저장합니다. 두 경로는 같은
`main` HEAD를 조건으로 보고서 파일 3개와 `content/publication/morning.json`을 한 커밋에서
갱신합니다. 경쟁하거나 Git 푸시 응답을 잃으면 원격 상태를 재조회합니다. 날짜별 결과는 한 번
선택되며, 늦은 안내가 선택된 연구를 바꾸거나 이전 날짜가 최신 포인터를 되돌릴 수 없습니다.

09:00 전에 검증과 결과 선택을 마친 연구만 장전 대상입니다. 검증된 장전 연구가 없으면 재시도할
수 있으며, 09:00부터는 수집기와 작성기를 호출하지 않고 기존 지연 안내를 사용합니다.
사이트가 09:00부터 홈의 당일 후보를 숨기는 기존 정책은 계속 적용됩니다. 실수집은 현재 KST
날짜만 허용합니다. 과거 날짜 테스트에는 `--dry-run`을 사용하세요.

Windows의 결과 커밋 푸시가 Pages workflow를 시작합니다. GitHub의 예약 수집은 같은 실행에서
Pages 단계로 이어집니다. Ubuntu job은 최신 선택 커밋을 체크아웃하고 패키징 시점에 재검증합니다.
`dist/publication.json`은 선택 커밋 SHA와 보고서 SHA-256을 노출합니다.
`daytrade-pages-receipts` 브랜치는 시도별 아티팩트 ID·다이제스트, Pages 배포 버전·ID,
관측 시각과 성공 여부를 Git 이력으로 보존합니다. `confirmed_before_cutoff`는 09:00 전에
당일 Pages 성공을 실제로 조회한 경우에만 참이며, 별도로 공개 URL도 대조할 수 있습니다.

`rebuild_only=true`는 미완료 Pages 배포를 복구합니다. 성공 영수증이 있는 결과는 그대로 유지합니다.
Pages 응답이 소실되면 기록된 배포 버전을 조회합니다. 공급자가 명시적으로 실패를 확정하면 새 버전으로
재시도할 수 있습니다. 조회에서 빈 상태나 404만 반환되면 해당 요청이 적용됐는지 확인할 수 없으므로
새 POST를 보내지 않습니다. 이 경우 기존 버전의 Pages 상태를 다시 확인하고 해소된 뒤 workflow를 재실행하세요.
선택적 Codex API PR 리뷰는 리포지토리 리뷰 키가 있을 때만 실행됩니다.

### Windows 등록 및 전환

전용 설치 경로에서 checkout과 Python 3.12 가상환경을 준비하고 `python -m pip install -e .`를
실행합니다. 수집 API 환경 파일은 기존 Daytrade 전용 비공개 파일을 재사용합니다. 등록은 비활성 상태에서
시작하며 현재 Windows 사용자, KST 고정 오프셋 및 기존 단일 작업 ID를 사용합니다.

```powershell
.\scripts\Set-MorningReportTask.ps1 -Mode RegisterDisabled -Checkout $checkout -Python $python -EnvironmentFile $privateEnv
.\scripts\Set-MorningReportTask.ps1 -Mode Status
```

등록 계정은 로그온 상태여야 합니다. 잠금 화면에서는 실행할 수 있습니다. 등록 계정은 GitHub에
대한 비대화식 Git 인증과 푸시·workflow 실행 권한도 갖춰야 합니다. Task Scheduler의 기록과
`private_artifacts/morning/logs/windows-YYYY-MM-DD.log`에서 실제 시작 시각을 확인하세요.

1. 거래일 정규 발행이 끝난 뒤 기존 `daily-report.yml` workflow를 비활성화하고 진행·대기 중인 실행을 모두 정리합니다. 전환 전의 workflow 실행은 다시 실행하지 않습니다.
2. 공통 게이트와 동일 cron을 가진 `morning-report.yml`을 기본 브랜치에 올립니다. 새 workflow가 활성 상태이고 이전 workflow가 비활성 상태인지 확인합니다.
3. 전용 체크아웃을 `origin/main`과 맞춘 뒤 `Set-MorningReportTask.ps1 -Mode Enable`을 실행합니다. 다음 실행 시각이 다음 거래 예정 평일의 08:45 KST인지 확인합니다.
4. 첫 거래일에는 08:45 시작 로그, 선택 SHA와 SHA-256, 아티팩트 ID·다이제스트, Pages 성공 영수증, 공개 `publication.json`과 `status.json`을 확인합니다.

Windows만 되돌릴 때는 `-Mode Disable`을 사용하면 공통 게이트가 있는 GitHub cron이 계속 운영됩니다.
완전 롤백은 Windows 작업을 비활성화하고 진행 중인 수집과 Pages 요청의 종결을 확인한 뒤 새 workflow를
비활성화합니다. 다음 거래일부터 이전 cron을 복원하며 기존 영수증과 당일 결과는 보존합니다.
`-Mode Unregister`는 비활성 작업만 제거합니다.

## 휴장일 설정

거래일은 `exchange-calendars`의 XKRX와 `config/holidays_kr.yml`의 검토된 변경일을 합칩니다.
2026년 지방선거·제헌절 변경을 반영했습니다. 예제 달력은 운영 근거로 사용하지 않습니다.
검토 범위 밖 연도는 `unknown`으로 처리하고 수집·후보 생성을 하지 않습니다.
2027년 5월 3일과 7월 19일은 우주항공청 월력요항에 명시된 대체공휴일이며 XKRX 4.13.2에
누락되어 변경일로 반영했습니다. 2027년 연말 휴장은 KRX 일반 휴장 규정을 적용한 일정입니다.
거래소의 연간 운영 공지와 임시 휴장을 추후 대조해야 합니다. 근거 URL은 설정 파일에 기록돼 있습니다.
휴장일에는 외부 수집기를 호출하지 않고 `Market Closed Note`를 생성합니다.

## 데이터 소스

- OpenDART: 국내 공시
- RSS/Naver/NewsAPI/Alpha Vantage/yfinance provider: 정치/정책, 글로벌 이슈, 테마 변동 후보
- 호환 quote provider: 가격, 등락률, 거래량, 거래대금, 실제 시세 시각
- yfinance fallback: 지연 정규장 가격과 제공된 시세 시각. 거래대금은 미제공 시 누락 처리
- mock collector: API 키 없는 테스트와 dry-run

데이터가 없거나 오래되면 값을 만들지 않고 `insufficient` 상태와 "데이터 부족" 문구를 사용합니다.

뉴스 수집은 `NEWS_RSS_URLS`, Naver Search News, NewsAPI.org, Alpha Vantage, yfinance를
순서대로 시도합니다. 설정의 회사명을 뉴스에 명시한 경우 KRX 코드에 연결합니다. 같은 기사 제목이나
원문 주소는 후보 점수에서 한 번 반영하며 관련 출처 ID는 보존합니다. yfinance는 키 없이 쓰는
보조 provider로 남겨두고, 한국어 뉴스 적합성이 높은 Naver Search API와 NewsAPI.org를 우선
사용합니다. 시세는 `QUOTE_PROVIDER_URL`이 있으면 우선 사용하고, 없으면 yfinance quote fallback을
사용합니다.

## 테스트

```powershell
ruff check .
pytest
```

## 검증 정책

검증기는 프로젝트 금지 문구, 출처 없는 수치, 가격 스냅샷 없는 가격 표현, 후보 목록에 없는
종목코드, 투자권유성 표현, 데이터 부족 상태에서의 확정 표현을 검사합니다. 공개 사이트에는 raw
provider 응답, secret, 개인 자산 정보, 포트폴리오 비중을 포함하지 않습니다.
저장 직전에도 실제 환경의 비밀값과 중첩 raw/token/account 필드를 검사해 공개 파일 생성을 거절합니다.
quote provider의 시장 문맥은 정해진 지표 스키마만 허용합니다.

수치와 단위가 인용된 이벤트/시세와 일치해야 합니다. 가격에는 스냅샷 ID와 기준 시각을
요구합니다. ISO 날짜와 시각은 통째로 검증하며 `1분기`와 `1분`을 구별합니다.
미래·시각 불명·48시간 초과 뉴스는 순위에서 제외합니다. 지연 정규장 시세는
주말을 감안해 최대 96시간 이내만 참고하고 장전 예상체결로 표현하지 않습니다.
OpenDART list가 접수일만 주면 시각을 생성하지 않으며 공시를 순위에서 제외합니다.
LLM 원고 실패 시 같은 입력의 결정적 facts writer를 독립 검증하고 이것도 실패하면 공지만 게시합니다.
실패 공지에는 후보·점수를 싣지 않습니다. 사이트 빌드에서도 기존 통과 원고를 재검증합니다.
홈과 `status.json`은 마지막 생성, 마지막 검증 연구, 현재 유효 연구를 구별합니다.
거래일 09:00 KST 전에 만든 검증된 장전 연구만 홈에서 활성화됩니다. 09:00 이후 패키징한 홈에는
후보 HTML이 생성되지 않습니다. 먼저 패키징한 페이지는 접속 시각 확인 뒤 후보를 표시하고 정각에 숨깁니다.
검증된 과거 연구는 날짜가 붙은 상세 페이지에서 열 수 있습니다. 합성 fixture는 후보를 공개하지 않습니다.

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
