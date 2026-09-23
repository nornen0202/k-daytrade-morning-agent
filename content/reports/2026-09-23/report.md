# 데이터 검증 실패 리포트 - 2026-09-23

생성 시각: 2026-09-23T10:46:07.071858+09:00

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
| SK hynix(000660) | 9.45 | source_id: src_1549ffdbdeb9, src_23ec57d47186, src_379067d5432b, src_9a314c38df27, src_a3c64a27df4f, src_c0f8d1dc156a, src_e36bcce1afcf, src_e98a0e0f3b6f; data_key: price_062db0e7b866 | none |
| KIWOOM(039490) | 8.66 | source_id: src_352a4dd87f7f, src_8490d6383287, src_d7e9e1a7ece5, src_e9c6e9bf6bcd; data_key: price_ad4632b45849 | none |
| AMOREPACIFIC(090430) | 8.65 | source_id: src_2b839ef5970f, src_530a9479cba1, src_6c58dc39d544, src_6fdbcdc15686, src_84e086485cc5, src_ccbbe8111406, src_d9bce5b7c807, src_f889b7fa8e76, src_f99e76a756af; data_key: price_b1e78e5a96d4 | none |
| NHIS(005940) | 8.63 | source_id: src_0fc7ddee4efc, src_3d2427229463, src_5f93949888cd, src_7c3c73fb8bc1, src_afe4b5c0c211, src_b9f1e9511ef4, src_bd7aad7cd708; data_key: price_09e74bd8c3db | none |
| KYOBOSECURITIES(030610) | 8.60 | source_id: src_4492ec085c67, src_4812510f26c0, src_558c5a65ac0a, src_63dd6fde71b1, src_64c55adf6196, src_6d873e837316, src_79516f55da90, src_9b8690e1f2cc, src_a2eb0c2bddef, src_b1c4b3426db3, src_df5e0620b2b9, src_e2202877827e, src_e602b94d4645; data_key: price_b51700950b65 | none |
| Biotoxtech(086040) | 8.24 | source_id: src_699084fd8bdd, src_d27a9e72a6d0; data_key: price_f513d07cd8f9 | none |
| SamsungElec(005930) | 7.59 | source_id: src_e5583e6adaa8, src_f1d9ae9c9a72; data_key: price_5db8f5c9e164 | none |
| NAVER(035420) | 7.11 | source_id: src_02a5775763d2, src_04223289db08, src_1c85c2dd4e6a, src_21afbeff3a44, src_7193f65d0093, src_ccbd90b3e6c5, src_cee4dba2feb0, src_e949a94cd14e; data_key: price_2ea0f857eba2 | none |
| Hansol IONES(114810) | 6.76 | source_id: src_c2a2aa0985c7; data_key: price_63c4776b100c | none |
| CHEMTRON(089010) | 6.75 | source_id: src_27560f0f64ad; data_key: price_0bbcdcaa6816 | none |

## 데이터 누락 및 확인 필요 사항

- yfinance quote unavailable for 003450
- yfinance quote unavailable for 008560
- yfinance quote unavailable for 008670
