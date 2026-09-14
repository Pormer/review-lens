# Agent API 사용법

실행 중인 서버의 `/docs`에서 OpenAPI 스키마를 볼 수 있습니다. 아래의 서비스 접근 키는 `APP_ACCESS_KEY`이며 OpenAI API 키와 다릅니다.

## 분석 생성

```bash
curl -X POST http://localhost:8000/api/analyses \
  -H 'Content-Type: application/json' \
  -H 'X-Access-Key: YOUR_SERVICE_ACCESS_KEY' \
  -d '{"product_name":"소니 WH-1000XM5","product_url":"https://www.coupang.com/vp/products/PRODUCT_ID","mode":"live"}'
```

`PRODUCT_ID`를 실제 상품 링크로 바꿔야 합니다. 키를 설정하지 않은 로컬 개발 환경에서는 `X-Access-Key`를 생략할 수 있습니다.

```json
{"id":"발급된-UUID","status":"queued"}
```

HTTP `202 Accepted`를 반환합니다. `mode`는 `live` 또는 `demo`이며 기본값은 `live`입니다. 예제 모드는 어떤 입력을 사용하더라도 고정된 가상 상품의 보고서를 반환합니다. 실제 모드는 선택한 제공자가 준비되지 않으면 `503`으로 실패하고 예제로 대체하지 않습니다. 기본 Ollama는 API 키 없이 로컬 모델을 사용합니다.

## 상태 조회

```bash
curl http://localhost:8000/api/analyses/JOB_ID -H 'X-Access-Key: YOUR_SERVICE_ACCESS_KEY'
```

`status`, `stage`, `created_at`, `updated_at`, `request`, `report`, `error`가 반환됩니다. 완료 이전에는 `report=null`, 실패 시 `error`에 사용자가 이해할 수 있는 메시지가 들어갑니다.

보고서의 주요 필드는 다음과 같습니다.

| 필드 | 의미 |
| --- | --- |
| `mode` | 실제 공개 웹 분석 또는 가상 예제 |
| `narrative` | 종합 의견, 장단점, 사용 경험, 구매 전 확인 사항 |
| `metrics` | 근거 수, 개별 리뷰 수, 표본 평균, 괴리 지표, 분포 |
| `evidence` | 검증을 통과한 근거. 로컬 모드의 `passage`는 수집 자료, OpenAI 선택 모드는 연구 메모의 발췌 |
| `sources` | 채택된 근거가 연결된 출처 |
| `discovered_sources` | 검색 응답이 인용한 전체 후보 출처. 채택 근거가 아닐 수도 있음 |
| `limitations` | 분석 범위와 불확실성 |
| `excluded_count` | 중복·상품 불일치·검증 실패로 제외된 근거 수 |

## 내보내기와 삭제

```bash
curl http://localhost:8000/api/analyses/JOB_ID/markdown \
  -H 'X-Access-Key: YOUR_SERVICE_ACCESS_KEY' -o report.md
curl -X DELETE http://localhost:8000/api/analyses/JOB_ID \
  -H 'X-Access-Key: YOUR_SERVICE_ACCESS_KEY'
```

삭제 성공은 `204`입니다. 실행 중인 작업은 삭제할 수 없고 `409`를 반환합니다. 데이터베이스에 결과가 남아 있는 동안만 조회·내보내기가 가능합니다. JSON은 상태 응답의 `report`를 저장하거나 웹의 JSON 버튼으로 받습니다.

## 오류 응답

| HTTP | 상황 |
| --- | --- |
| 401 | 서비스 접근 키가 없거나 잘못됨 |
| 404 | 없는 ID, 삭제됐거나 만료된 리포트 |
| 409 | 실행 중 삭제, 미완료 리포트 내보내기 |
| 413 | 명시된 Content-Length가 16 KiB를 초과함 |
| 422 | 상품명·URL·모드·UUID 형식 오류 |
| 429 | 대기열 또는 시간당 서버 호출 한도 초과 |
| 503 | 실제 분석 설정 미완료 |

작업이 접수된 후의 외부 API 오류는 HTTP 조회 자체가 실패하는 대신 작업 상태가 `failed`가 됩니다. 리버스 프록시에서도 업로드 크기·속도 제한을 설정하는 것이 좋습니다.

`/api/config`는 키 값 없이 제공자·모델·준비 여부와 예제 정보를 공개합니다. Ollama는 모델 설치 여부를 확인합니다. `/healthz`는 서버 생존 상태만 반환합니다. OpenAI 키의 실제 유효성까지 검증하는 엔드포인트는 아닙니다.
