# 데이터 검증 실패 리포트 - 2026-04-27

생성 시각: 2026-04-27T06:55:00.607773+09:00

> 이 리포트는 공개 데이터 기반 의사결정 보조 자료이며 투자 조언이 아닙니다.

## 검증 실패 이유

- price-like claim lacks price_snapshot data_key

## 경고

- report data_status is partial
- missing data was reported

## 공개 가능한 후보 요약

| 후보 | 점수 | 근거 | 리스크 |
| --- | ---: | --- | --- |
| 065420(065420) | 4.44 | source_id: src_41454a1d00b7; data_key: 데이터 부족 | missing_price_snapshot |

## 데이터 누락 및 확인 필요 사항

- price_snapshot: QUOTE_PROVIDER_URL is not configured
