# 공식 API 전환과 AI 역할

확인일: 2026-09-14. 공식 API는 자료를 제공하며 장단점·감성 해석까지 대신하지는 않습니다.

## 최신 서비스 변경

네이버 쇼핑·책·전문자료 검색 API는 2026년 7월 31일 종료됐습니다. 블로그·웹문서 검색 신규 신청도 NAVER API HUB로 이전했습니다. 이전 네이버 개발자센터 설명과 API 명세가 검색에 남아 있어도 신규 연동에 사용하지 않습니다.

- [종료 공지](https://developers.naver.com/notice/article/32564)
- [API HUB 이관 공지](https://developers.naver.com/notice/article/32530)

## 기능별 대체 결과

| 기능 | 현재 처리와 판단 |
| --- | --- |
| 블로그 사용기 탐색 | NAVER API HUB 블로그 검색 API로 대체 가능. 제목·요약·링크 제공 |
| 일반 웹·다른 쇼핑몰 출처 탐색 | NAVER API HUB 웹문서 검색 API로 대체 가능. 전체 리뷰를 제공하지는 않음 |
| 상품 정보·가격 | 종료된 쇼핑 검색 API는 연결하지 않음. 기존 접근 가능한 공개 페이지의 본문·구조화 정보를 활용 |
| 개별 구매 리뷰·별점 | 임의 상품의 여러 쇼핑몰 리뷰를 통합 제공하는 범용 공식 API를 확인하지 못함. 접근 가능한 원문에서 함께 확인된 값만 사용 |
| 원문 확보 | 검색 API는 본문 전체를 제공하지 않아 기존 공개 페이지 수집 유지. 제한되면 검색 요약만 사용 |
| 상품 일치·후기 유형·감성 | AI가 분석. 검색 결과만으로 정확한 모델·세대를 확정하지 않음 |
| 장단점·사용 경험·한국어 리포트 | AI가 수집된 근거로 작성 |
| 평균·표본 수·중복 제거·별점 괴리 | 이미 서버 코드로 계산하며 외부 API 추가 불필요 |
| 저장·내보내기·인증·작업 큐 | 기존 코드 유지. 자료 수집 API로 대체할 기능이 아님 |

네이버 커머스API와 쿠팡 판매자 Open API는 판매자·애플리케이션 권한을 전제로 합니다. 제휴 상품 API 역시 전체 리뷰 API와 다르며 이번 버전에 연결하지 않았습니다. G마켓도 임의 상품 전체 리뷰용 범용 공식 API를 확인하지 못해 어댑터를 추가하지 않았습니다. Shopping Insight는 클릭 트렌드 API로, 상품 상세·구매 리뷰 수집을 대체하지 않습니다.

## 발급·설정

1. [네이버 클라우드 플랫폼](https://www.ncloud.com/) 계정으로 콘솔에 접속합니다. 계정 등록·인증·약관 확인은 계정 소유자가 진행합니다.
2. All Services → Application Services → NAVER API HUB → Application으로 이동합니다.
3. Application 등록에서 NAVER 검색의 **블로그·웹문서**를 선택합니다.
4. 앱 이름은 `review-lens`로 입력합니다. API별 요금 안내와 이용 조건을 확인한 뒤 등록합니다.
5. 앱의 인증 정보에서 Client ID와 Client Secret을 확인합니다. NCP 계정의 일반 Access Key가 아닌 **API HUB 앱 인증 정보**입니다.
6. 프로젝트 `.env`에 다음을 입력합니다. 키는 채팅·GitHub·프런트엔드 코드에 넣지 않습니다.

```dotenv
SEARCH_PROVIDER=naver
NAVER_CLIENT_ID=API_HUB_Client_ID
NAVER_CLIENT_SECRET=API_HUB_Client_Secret
```

7. 서버를 재시작합니다. `/api/config`의 `search_provider=naver`를 확인합니다. 키 값은 응답에 포함하지 않습니다.
8. Ollama 또는 명시적으로 선택한 OpenAI를 준비하고 실제 상품 분석의 출처와 한계를 검토합니다.

## 비용과 한도

2026-09-14에 확인한 [API HUB 공식 개요](https://guide.ncloud-docs.com/docs/apihub-overview)는 **한시적 무료 제공**이며 유료 전환 전에 별도 공지한다고 안내합니다. 영구 무료로 가정하지 않습니다. 같은 개요의 최신 FAQ는 NAVER 검색 호출 한도를 **월 합산 최대 775,000건**, 도달 시 차단으로 안내합니다. 일부 개별 API 명세에는 종전 일 25,000회 설명이 남아 있으므로 실제 콘솔의 적용 한도와 요금 안내를 확인합니다.

이 구현은 분석 작업당 블로그·웹문서 요청을 각각 한 번씩 **총 2회** 호출하며 각 3개 결과를 받습니다. 월 분석 100건이면 검색 요청은 200회입니다. API 키를 다른 서비스에서도 사용하면 합산됩니다.

API HUB 앱의 **한도 및 알림**에서 일·월 한도와 알림을 설정할 수 있습니다. 실제 계정의 요금 상태를 확인한 뒤 사용합니다. 코드의 시간당 분석 제한은 별도 서비스 사용이나 장기 예산까지 통제하는 월 비용 상한은 아닙니다.

- Ollama: 유료 AI API 호출 없음. 모델 실행 자원과 전기 필요.
- OpenAI: 네이버 경로는 내장 유료 웹 검색을 생략하지만 **추출·요약 토큰 비용은 발생**. 최대 6회 추출과 최대 1회 종합 요청이며 재시도 비용이 추가될 수 있음.
- 웹서버 호스팅: 선택한 호스팅의 비용·무료 조건은 별도.

## 수집 경로 선택

`SEARCH_PROVIDER=auto`는 네이버 키가 있으면 API HUB를 선택하고, 없으면 기존 동작(Ollama: DDGS, OpenAI: 내장 웹 검색)을 유지합니다. `naver`를 명시하면 키 누락은 오류이고, API 실패 시 DDGS나 유료 웹 검색으로 자동 전환하지 않습니다. `ddgs`를 명시하면 두 AI 제공자 모두 코드가 수집한 자료만 분석합니다.

API HUB 키를 설정해도 `AI_PROVIDER`는 자동으로 바뀌지 않습니다. API 자체가 AI를 대체하지 않기 때문에 실제 분석에는 선택한 모델이 필요합니다.

## 데이터 처리와 검증

- 공식 검색 요약과 직접 수집한 페이지 본문을 구분합니다. 원문을 확보하지 못한 API 요약은 개별 리뷰·별점·구매 인증의 근거로 채택하지 않습니다.
- 검색·원문 모두 신뢰하지 않는 자료로 처리하고, AI 발췌·출처·상품 일치·중복 검증을 유지합니다.
- 원문은 기존 robots/DNS/크기/시간 제한을 지킵니다. API를 쓸 수 있다고 연결된 사이트의 접근 제한을 우회하지 않습니다.
- 인증 헤더는 고정된 `naverapihub.apigw.ntruss.com`에만 전달합니다. 리디렉션을 따르지 않고, 공개 페이지 수집에 키를 전달하지 않습니다.
- 401: 앱 인증·API 선택 확인. 403: 호출 조건·권한 확인. 429: 사용 한도 확인. 보고서에는 실패 종류만 표시하고 키·응답 본문은 노출하지 않습니다.
- 공식 API도 모든 쇼핑몰·상품·원문을 찾는다는 보장은 없습니다. 개별 리뷰가 부족하면 별점 통계가 산출되지 않을 수 있습니다.
- 모의 HTTP·모델 테스트를 수행했습니다. 실제 API HUB 키와 AI 모델을 이용한 전체 분석은 아직 검증 전입니다.

## 공식 자료

- [현재 API·인증·키 발급](https://api.ncloud-docs.com/docs/naver-api-hub-overview)
- [앱 등록·이용 한도 설정](https://guide.ncloud-docs.com/docs/apihub-application)
- [블로그 API](https://api.ncloud-docs.com/docs/naver-api-hub-search-blog)
- [웹문서 API](https://api.ncloud-docs.com/docs/naver-api-hub-search-webkr)
- [네이버 커머스API](https://apicenter.commerce.naver.com/docs/commerce-api/current)
- [쿠팡 공식 API 목록](https://developers.coupang.com/ko/api)
