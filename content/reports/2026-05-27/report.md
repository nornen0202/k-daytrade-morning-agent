# 데이터 검증 실패 리포트 - 2026-05-27

생성 시각: 2026-05-27T10:37:39.454118+09:00

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
| SK hynix(000660) | 9.45 | source_id: src_090e3a55a64b, src_47a9f5c2ffda, src_69b7ca6920be, src_6a58e2f685dc, src_93bc84d0da58, src_a400457a1635, src_b5b152c19e22, src_d388b03d600f; data_key: price_ff0392e03cd8 | none |
| SamsungHvyInd(010140) | 9.32 | source_id: src_070d52029f58, src_2e3be4d9dc59, src_42e55406ab8f; data_key: price_528a5c52f993 | none |
| NAVER(035420) | 9.14 | source_id: src_1badbe665e62, src_3a80b1785c33, src_6d21c084e39a, src_7e73cc753cac, src_91347c9ea019, src_a3e876f340c1, src_e60cf95cfe65; data_key: price_4cd894c4f785 | none |
| SamsungElec(005930) | 9.09 | source_id: src_1cf78c6d47d9, src_479ac146583d, src_87786339553f; data_key: price_20c082170bff | none |
| HANSOL HOLDINGS(004150) | 8.26 | source_id: src_52510fef4e6f, src_cb1c7e798c33; data_key: price_e057fa58dfba | none |
| 3ALogics(177900) | 8.24 | source_id: src_9a694a398edc, src_fe3ca81bed3e; data_key: price_9d8ee92f6955 | none |
| KT&G(033780) | 6.96 | source_id: src_8bfa04ba44d6; data_key: price_ba19401f3597 | none |
| Pharmicell(005690) | 6.80 | source_id: src_b31001f548eb; data_key: price_5c9cca497779 | none |
| Netmarble(251270) | 6.78 | source_id: src_f8272e549c11; data_key: price_20e9f1a7690f | none |
| Iron Device(464500) | 6.75 | source_id: src_8d2b10be060d; data_key: price_a190f7408c79 | none |

## 데이터 누락 및 확인 필요 사항

- yfinance quote unavailable for 0009K0
- yfinance quote unavailable for 003450
