# 데이터 검증 실패 리포트 - 2026-07-10

생성 시각: 2026-07-10T10:14:36.476333+09:00

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
| SK hynix(000660) | 9.80 | source_id: src_14e314b99cee, src_176c04022ecf, src_19875af00688, src_23553817b889, src_2bd29c593c89, src_3486d5009ae3, src_398f682095fe, src_3bcfa917c67d, src_5698298712fc, src_8cbf51cb0238, src_9c9828621f77, src_aff5bbbde866, src_c1e9dd305093, src_fed0a27755e0; data_key: price_ab8e71b1b2e7 | none |
| SKSQUARE(402340) | 9.70 | source_id: src_05710b08f052, src_3d32bf246ae7, src_d03a2a23e5d5; data_key: price_74b5def0ae06 | none |
| SamsungElec(005930) | 9.45 | source_id: src_173b91980e06, src_2e7ed9bb71ca, src_3ae8c3c14791, src_4f721041fc07, src_ad8d0cfb6a09, src_e0db1ef89fcc, src_f2bfb570c625; data_key: price_37774721e03e | none |
| SamsungSecu(016360) | 8.57 | source_id: src_4c418425c4cb, src_e814e2b061a3; data_key: price_d6f0606aa0e2 | none |
| KYOBOSECURITIES(030610) | 8.24 | source_id: src_1fb6f0d233b2, src_cc81bb9514a4; data_key: price_5fa7f3b92a64 | none |
| HANDOK(002390) | 8.24 | source_id: src_3687e094f990, src_d72ee8d86543; data_key: price_c1bb16e1b160 | none |
| HD HYUNDAI HEAVY INDUSTRIES(329180) | 7.10 | source_id: src_a4ccbb5d5d05; data_key: price_c6cc906b951a | none |
| NAVER(035420) | 6.98 | source_id: src_733ae0ef1278, src_84c0947e0d78, src_859c937eb85f, src_86c87981131d, src_9ab1858490d9, src_d90a2828ba84, src_e7e84335ad0c, src_fae3b975fb53; data_key: price_eb1c33b611f4 | none |
| Kakao(035720) | 6.85 | source_id: src_4a189aef1367, src_67b4b24cef29, src_931d84ad317b, src_9ff3386d6ac7, src_d8f92996b59d, src_e5fc81948ad4, src_f73ccdc513c6, src_fb373f50dd29; data_key: price_32f3fb5f3602 | none |
| NHIS(005940) | 6.83 | source_id: src_ff7a1bdff446; data_key: price_b61d4260de7e | none |

## 데이터 누락 및 확인 필요 사항

- yfinance quote unavailable for 0037T0
- yfinance quote unavailable for 008560
- yfinance quote unavailable for 192520
- yfinance quote unavailable for 496320
