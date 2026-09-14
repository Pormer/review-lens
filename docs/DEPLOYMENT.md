# 배포 가이드

## 1. Docker로 실행

Docker Desktop 또는 Docker Engine이 설치되어 있어야 합니다.

```bash
cp .env.example .env
# .env의 Ollama 연결 주소 및 24자 이상의 APP_ACCESS_KEY 설정
docker compose up -d --build
docker compose logs -f
```

Windows에서는 `Copy-Item .env.example .env`를 사용합니다. `.env`가 이미 있다면 복사하지 않습니다. [localhost:8000](http://localhost:8000)에서 확인합니다. 이미지에는 `.env`, Git 정보, 로컬 DB와 테스트 데이터가 포함되지 않습니다. 컨테이너는 일반 사용자 권한으로 실행되며 데이터는 `reviewlens-data` 볼륨에 저장합니다.

```bash
docker compose down
```

위 명령은 볼륨을 유지합니다. `down -v`는 데이터를 삭제하므로 백업 없이 실행하지 않습니다.

## 2. Render 평가용 배포

계정이 없다면 먼저 Render에 가입해야 합니다. 이 저장소의 `render.yaml`은 **예제 리포트 평가용** 무료 플랜을 명시합니다. 이 작은 인스턴스에는 로컬 모델을 포함하지 않으므로 실제 Ollama 분석은 작동하지 않습니다. 실제 분석은 [로컬 AI 가이드](LOCAL_AI.md)의 PC/서버 구성을 사용합니다. 가입, 서비스 연결, 약관 동의 및 비용이 수반되는 선택은 계정 소유자가 확인해야 합니다.

1. [Render Dashboard](https://dashboard.render.com/)에서 GitHub 저장소를 연결합니다.
2. Blueprint로 `Pormer/review-lens`의 `render.yaml`을 선택하거나 새 Docker Web Service를 만듭니다.
3. 기본 `AI_PROVIDER=ollama`를 유지합니다. 예제 평가는 API 키를 요구하지 않습니다.
4. 자동 생성된 `APP_ACCESS_KEY`를 확인하고 웹의 서비스 설정에 입력합니다. OpenAI 키와 혼동하지 않습니다.
5. 헬스 체크 경로는 `/healthz`입니다. Dockerfile이 Render의 `PORT` 값을 사용합니다.
6. 배포가 완료되면 발급된 HTTPS 주소에서 예제 분석, 기록, 내보내기를 확인합니다.
7. 실제 분석이 필요하면 별도로 모델을 실행할 충분한 자원과 안전한 연결을 준비하고, 정확한 상품명·링크로 출처와 수집 한계를 검토합니다. 유료 OpenAI 전환은 사용자가 명시적으로 선택할 때만 진행합니다.

**무료 인스턴스의 파일 저장소는 영구 저장소가 아닙니다.** 재시작·재배포 시 SQLite 기록이 사라질 수 있으며 비활성 상태의 서비스가 중지될 수 있습니다. 서버 내 7일 보관 설정은 영구 저장을 보장하지 않습니다. 지속 운영은 지원되는 유료 디스크와 `DATABASE_PATH`를 설정하거나 외부 DB·큐로 전환해야 합니다. 유료 구성을 자동 신청하지 않습니다.

공개 페이지에서 누구나 모델 자원이나 선택형 API 비용을 소비하지 않도록 `APP_ENV=production`에서는 24자 이상의 서비스 접근 키가 없으면 실제 분석을 비활성화합니다. 이 키는 신뢰할 수 있는 평가자에게만 전달합니다.

## 3. 운영 시 지킬 실행 조건

- **하나의 서비스 인스턴스와 `--workers 1`**: 메모리 큐와 재시작 복구는 이 구성을 전제로 합니다.
- 리버스 프록시의 HTTPS, 요청 크기 제한, 접근 로그의 민감한 쿼리 마스킹
- 환경 변수 기반 비밀 관리, OpenAI 프로젝트 예산 제한
- 영구 디스크 백업, 복구 시험, 디스크 용량 관측
- 운영 데이터에는 개인정보가 없는 공개 상품 링크만 사용

## 4. 배포 완료 확인 목록

- [ ] GitHub Actions의 테스트와 Docker 스모크 테스트 통과
- [ ] 배포 URL에서 `/healthz`가 `{"status":"ok"}` 반환
- [ ] 브라우저 화면, 예제 작업, Markdown·JSON 다운로드 정상
- [ ] 잘못된 서비스 접근 키는 401, 잘못된 링크는 422
- [ ] 실제 상품 분석 1건 및 근거 링크 확인
- [ ] 재시작 시 저장 상태 및 영구 저장소 조건 확인
- [ ] 공개 URL을 README·블로그 글에 추가

실행하지 않은 항목을 완료로 표시하지 않습니다.

공식 자료: [FastAPI 컨테이너](https://fastapi.tiangolo.com/deployment/docker/), [Render FastAPI](https://render.com/docs/deploy-fastapi), [Render Blueprint](https://render.com/docs/blueprint-spec), [Render 무료 인스턴스](https://render.com/docs/free).
