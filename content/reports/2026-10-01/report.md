# 데이터 검증 실패 리포트 - 2026-10-01

생성 시각: 2026-10-01T11:24:01.840867+09:00

> 이 리포트는 공개 데이터 기반 의사결정 보조 자료이며 투자 조언이 아닙니다.

## 검증 실패 이유

- investment-pressure wording found
- unknown symbol mentioned: 128800, 201000, 262250, 268250, 294000
- price-like claim lacks price_snapshot data_key
- numeric material claim lacks source_id or data_key

## 경고

- report data_status is partial
- missing data was reported

## 공개 가능한 후보 요약

| 후보 | 점수 | 근거 | 리스크 |
| --- | ---: | --- | --- |
| SK hynix(000660) | 9.45 | source_id: src_3d2bcd4585eb, src_5020b325e8ae, src_67644df2a6b7, src_7b2674e3432d, src_9ca6a8c37610, src_c8b16c64958b, src_cace0dec6966, src_eba06e7a4224; data_key: price_267ddc7ef27e | none |
| SamsungElec(005930) | 8.95 | source_id: src_1b8397f1a806, src_2e29fdb317de, src_4241bfc3eac7, src_aba7c2a6caaa, src_cfb363fe9571, src_d73dc79e7b4c, src_e83efe8ee76b; data_key: price_a89830e8b5ed | none |
| MIRAE ASSET SEC(006800) | 8.69 | source_id: src_4e74893346d7, src_64b898dad59f, src_8211b19cf2b7, src_e5dacc5a4b32, src_f0e185af6106; data_key: price_87a965597fc6 | none |
| Kakao(035720) | 8.68 | source_id: src_00af98415c46, src_2f1400de7dd0, src_3bb6736f46ac, src_931d84ad317b, src_93aec78726a5, src_9ff3386d6ac7, src_b4b49825b851, src_bbd6e485c5fa, src_e5fc81948ad4; data_key: price_471500f1eaa8 | none |
| HANAFINANCIALGR(086790) | 8.59 | source_id: src_1ab93c8366e0, src_569172f368de; data_key: price_91f76ccdd6c1 | none |
| 900290(900290) | 8.50 | source_id: src_0e2604194c44, src_89b25d337fdc, src_9027d87acc89, src_a8578eaf236b; data_key: price_af23a9b7ee64 | none |
| 296640(296640) | 8.39 | source_id: src_94892025ad0b, src_aea78ba13636, src_f0629f1c4870; data_key: price_04180deeb918 | none |
| LG Display(034220) | 8.31 | source_id: src_7da617c56f9c, src_f8e366048b26; data_key: price_9dae66df5f76 | none |
| NH Prime REIT(338100) | 8.24 | source_id: src_771a5f4ff5d9, src_bf19308d96d7; data_key: price_adb74f697c67 | none |
| NHALLONEREIT(400760) | 8.24 | source_id: src_79c2321e0fcf, src_df28c4e1d406; data_key: price_f4099159a2c5 | none |

## 데이터 누락 및 확인 필요 사항

- yfinance quote unavailable for 000010
- yfinance quote unavailable for 001590
- yfinance quote unavailable for 003450
