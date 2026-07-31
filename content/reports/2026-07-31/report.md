# 데이터 검증 실패 리포트 - 2026-07-31

생성 시각: 2026-07-31T10:10:56.477011+09:00

> 이 리포트는 공개 데이터 기반 의사결정 보조 자료이며 투자 조언이 아닙니다.

## 검증 실패 이유

- investment-pressure wording found
- price-like claim lacks price_snapshot data_key
- numeric material claim lacks source_id or data_key

## 경고

- report data_status is partial
- missing data was reported

## 공개 가능한 후보 요약

| 후보 | 점수 | 근거 | 리스크 |
| --- | ---: | --- | --- |
| LG CNS(064400) | 8.64 | source_id: src_a7b575014e96, src_b0896c5d7c96; data_key: price_88dfcf313a38 | none |
| KYOBOSECURITIES(030610) | 8.60 | source_id: src_5ab9bd0db272, src_7a7aafe33914, src_c9aa89c9f52c, src_cb5b95843f7a, src_d0a7c8ced944, src_d76a7d9f033f; data_key: price_e7f831e91421 | none |
| PanOcean(028670) | 8.29 | source_id: src_762163abe41b, src_fc6e1c218e8f; data_key: price_ed992691e729 | none |
| HMSEC(001500) | 8.24 | source_id: src_52eabc48e487, src_8bcbf26bce3c; data_key: price_c6af47e4ac59 | none |
| SK hynix(000660) | 7.90 | source_id: src_20e98c9dca25, src_29ec9a70e051, src_381e3e781659, src_41be7a97c817, src_474b8c3bf7b3, src_49dd4d0da03b, src_634565f66390, src_d60e104da496, src_ddbddb47c421; data_key: price_61c1bbb85ca2 | high_volatility |
| DaewonCbl(006340) | 7.80 | source_id: src_2c35ba102e12, src_461d162e8652, src_5fcc3fb3374c, src_6d75f9dc8013, src_b417d0f950a3; data_key: price_e0a78980c32e | high_volatility |
| SamsungElec(005930) | 7.55 | source_id: src_21e1cf17b86b, src_4439b316cf9c, src_5e16b24a7179, src_78589e229908, src_87644282a1df, src_89e6472e43dc; data_key: price_4da68aed37af | high_volatility |
| Hanwha Ocean(042660) | 7.45 | source_id: src_b3e6833d6fa0; data_key: price_184fb2168b08 | none |
| NAVER(035420) | 7.35 | source_id: src_1a36f703cef6, src_2613a4cfe353, src_4039993101ef, src_7193f65d0093, src_bfbe508d6a78, src_cee4dba2feb0, src_e949a94cd14e, src_fddd6e75929f; data_key: price_0987b8b6e003 | none |
| MIRAE ASSET SEC(006800) | 6.93 | source_id: src_422f517b5f7d, src_55d9ba907e52, src_7fbe918261e4; data_key: price_dadc8a4fea74 | high_volatility |

## 데이터 누락 및 확인 필요 사항

- yfinance quote unavailable for 0218L0
