# API 요금 없는 로컬 AI 실행

기본 제공자는 `ollama`입니다. **OpenAI API 키를 넣지 않아도 되고 호출당 API 요금도 없습니다.** 웹 검색에는 인터넷이 필요하며 모델 추론은 본인 PC의 CPU/GPU를 사용합니다. 전기·인터넷·하드웨어·외부 호스팅 비용까지 0원임을 의미하지는 않습니다.

## 설치

1. [Ollama 공식 다운로드](https://ollama.com/download/windows)에서 Windows용 프로그램을 설치합니다.
2. 터미널에서 모델을 받습니다. 예시는 다국어 모델 `qwen2.5:3b`입니다.

```powershell
ollama pull qwen2.5:3b
ollama list
```

Ollama는 모델과 실행 파일을 위해 수 GB의 디스크 공간을 사용합니다. 더 큰 모델은 품질을 높일 수 있지만 RAM·VRAM 사용량과 지연이 증가합니다. 다른 모델을 선택하면 `.env`의 `OLLAMA_MODEL`도 같은 이름으로 바꿉니다.

3. `.env`에 아래 설정을 둡니다.

```dotenv
AI_PROVIDER=ollama
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=qwen2.5:3b
JOB_TIMEOUT_SECONDS=600
OPENAI_API_KEY=
```

4. Ollama가 실행 중인 상태에서 리뷰렌즈 서버를 시작합니다. 필요하면 별도 터미널에서 `ollama serve`를 실행합니다. 이미 서버가 켜져 있으면 중복 실행하지 않습니다.
5. 웹 화면을 새로고침하고 ‘로컬 AI 준비됨’ 표시를 확인한 뒤 상품을 분석합니다.

## 실제 동작

- DDGS가 공개 검색 엔진에 상품명 검색어를 보냅니다. 별도 유료 검색 API 키는 사용하지 않습니다.
- 입력 구매 링크와 검색된 공개 페이지를 제한된 범위에서 읽습니다.
- robots.txt 정책, HTTP 오류, 페이지 크기·리디렉션·시간 제한을 적용합니다. 접근 차단을 우회하지 않습니다.
- DNS 결과의 공인 IP만 허용하고 해당 IP로 연결하면서 원래 TLS 호스트를 유지해 내부망 접근과 DNS 재바인딩을 막습니다.
- JSON-LD의 개별 리뷰 별점을 상품 전체 집계 별점과 구분합니다.
- 각 페이지를 작은 묶음으로 로컬 모델에 보내고 Pydantic 스키마·출처·발췌를 검증합니다.
- 자료를 모으지 못하거나 작은 모델이 형식을 지키지 못하면 근거 부족 또는 오류로 표시합니다.

무료 검색은 비공식 라이브러리를 사용하므로 검색 엔진의 정책·접근 제한·변경에 영향을 받습니다. 검색 결과의 단편만으로는 리뷰 원문이나 개별 별점을 얻지 못할 수 있습니다. 확보된 출처와 실제 근거 수를 반드시 확인합니다.

## Docker에서 호스트 PC의 Ollama 연결

Windows/macOS Docker Desktop은 다음 주소를 사용할 수 있습니다.

```dotenv
OLLAMA_BASE_URL=http://host.docker.internal:11434
```

컨테이너에서 접근하려면 Ollama가 그 인터페이스에서 요청을 받을 수 있어야 합니다. 기본 루프백 바인딩만 있는 환경에서는 연결되지 않을 수 있습니다. 외부 네트워크에 Ollama를 공개하지 말고 방화벽과 접근 범위를 확인하세요. 가장 단순한 실행은 리뷰렌즈와 Ollama를 둘 다 호스트 PC에서 실행하는 것입니다.

## 공개 배포와의 관계

무료 Render의 작은 인스턴스에 로컬 대형 모델을 함께 실행하는 구성이 아닙니다. Render 템플릿은 **예제 화면 평가용**으로 사용할 수 있으며, 실제 로컬 분석 공개 서비스에는 모델을 실행할 자원과 안전한 연결이 필요합니다. 소유한 PC나 서버에서 운영하거나, 충분한 자원을 제공하는 호스팅을 선택해야 합니다. 이 프로젝트는 비용이 발생하는 호스팅을 자동 신청하지 않습니다.

## 선택 사항: OpenAI

원할 때만 `AI_PROVIDER=openai`와 `OPENAI_API_KEY`를 설정합니다. 기본 로컬 모드가 실패해도 유료 API로 자동 전환하지 않습니다. 공개 검색의 페이지 본문은 로컬 모드에서 OpenAI로 전송하지 않습니다.

공식 참고: [Ollama Windows](https://docs.ollama.com/windows), [구조화 출력](https://docs.ollama.com/capabilities/structured-outputs), [DDGS](https://github.com/deedy5/ddgs).
