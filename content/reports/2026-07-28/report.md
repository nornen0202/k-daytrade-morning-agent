# 데이터 검증 실패 리포트 - 2026-07-28

생성 시각: 2026-07-28T10:01:23.974554+09:00

> 이 리포트는 공개 데이터 기반 의사결정 보조 자료이며 투자 조언이 아닙니다.

## 검증 실패 이유

- price-like claim lacks price_snapshot data_key
- numeric material claim lacks source_id or data_key

## 경고

- report data_status is partial
- missing data was reported

## 공개 가능한 후보 요약

| 후보 | 점수 | 근거 | 리스크 |
| --- | ---: | --- | --- |
| NAVER(035420) | 9.35 | source_id: src_1a36f703cef6, src_2613a4cfe353, src_4039993101ef, src_7193f65d0093, src_bfbe508d6a78, src_cee4dba2feb0, src_e949a94cd14e, src_fddd6e75929f; data_key: price_65094c93ce0a | none |
| NHIS(005940) | 8.27 | source_id: src_4cf0c760631c, src_f6167071df35; data_key: price_983f260c3282 | none |
| TBH GLOBAL(084870) | 8.24 | source_id: src_07e421bb8827, src_e4f839f97947; data_key: price_125bd4e65c75 | none |
| KYOBOSECURITIES(030610) | 8.24 | source_id: src_523ba572e441, src_ba3b637fda3a; data_key: price_daaa29086b62 | none |
| SK hynix(000660) | 7.55 | source_id: src_203fe4881656, src_496e3423cd7c, src_7cc8de190f24, src_92f60413a156, src_cc2471427559, src_cc33a41981f4, src_e3aa9419428a, src_f9b534ea9abe; data_key: price_fac8afd9ff94 | high_volatility |
| SamsungElec(005930) | 7.55 | source_id: src_086b72cfb675, src_63cf5736d979, src_d357345a7f64, src_d5fe2ac06087; data_key: price_7efe237775da | high_volatility |
| PIAM(178920) | 6.75 | source_id: src_ffa2c5e1bef1; data_key: price_facdc45fe695 | none |
| Donga ST(170900) | 6.74 | source_id: src_5de343594d3f; data_key: price_446c214e85ce | none |
| 396300(396300) | 6.64 | source_id: src_6f23fb1a149c; data_key: price_0f6f8cbd0811 | none |
| Kakao(035720) | 6.51 | source_id: src_3bb6736f46ac, src_4a189aef1367, src_931d84ad317b, src_9ff3386d6ac7, src_d8f92996b59d, src_e5fc81948ad4, src_f73ccdc513c6, src_fb373f50dd29; data_key: price_3ff5854016d4 | none |

## 데이터 누락 및 확인 필요 사항

- yfinance quote unavailable for 134780
