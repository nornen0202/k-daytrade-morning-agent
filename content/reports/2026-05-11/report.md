# 데이터 검증 실패 리포트 - 2026-05-11

생성 시각: 2026-05-11T10:29:55.822174+09:00

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
| SamsungElec(005930) | 9.80 | source_id: src_12b4c7956a8f, src_59ba0e68b46b, src_7b98a3be5caa, src_82e1ec269a86, src_82f9bd6de0bd, src_91d19a5c559a, src_b8075508270b; data_key: price_56d9c0491604 | none |
| Yuhan(000100) | 8.57 | source_id: src_44516f5c1e62, src_55940293cf30, src_fb5d58e24915; data_key: price_a61ec09c0ca9 | none |
| S-1(012750) | 8.51 | source_id: src_13d57d7706e5, src_1586ce3aff58, src_ca8b8c7f2e1d; data_key: price_b90e87c9e1b4 | none |
| Hanwha Ocean(042660) | 7.94 | source_id: src_a7029ac29c15; data_key: price_2e2880ddbf38 | none |
| 006400(006400) | 7.94 | source_id: src_b3fa0d97a67b; data_key: price_794b94d1c1af | none |
| Blue Industrial Development(006740) | 7.90 | source_id: src_355000663bfd, src_653b2209e949, src_7802731e251c, src_8b0187f3ebd4, src_c398cac02bb1; data_key: price_f1189d046137 | none |
| HANMISemi(042700) | 7.84 | source_id: src_96d2d8ad7308; data_key: price_d2be354b5a0b | none |
| MIRAE ASSET SEC(006800) | 7.84 | source_id: src_0e67c5db10ea; data_key: price_133348b8c6a6 | none |
| KIWOOM(039490) | 7.35 | source_id: src_d0d8c2b8b38f; data_key: price_8edde2b54a2e | none |
| NAVER(035420) | 7.16 | source_id: src_1badbe665e62, src_2b92253e768b, src_6d21c084e39a, src_7e73cc753cac, src_91347c9ea019, src_e60cf95cfe65; data_key: price_2efdad799c53 | none |

## 데이터 누락 및 확인 필요 사항

- yfinance quote unavailable for 0015S0
- yfinance quote unavailable for 003450
