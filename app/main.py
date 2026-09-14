import asyncio
import logging
import secrets
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from openai import APIConnectionError, AuthenticationError, RateLimitError

from app.agent import run_live
from app.config import Settings
from app.demo import DEMO_NAME, DEMO_URL, demo_report
from app.export import markdown_report
from app.local_agent import local_ready
from app.models import AnalysisRequest
from app.storage import Store

logger = logging.getLogger(__name__)
STATIC = Path(__file__).parent / "static"


def create_app(settings: Settings | None = None, live_runner=run_live) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.store = Store(settings.database_path)
        app.state.store.recover(settings.retention_days)
        app.state.queue = asyncio.Queue(maxsize=settings.max_pending_jobs)

        async def worker():
            while True:
                job_id, payload = await app.state.queue.get()
                store = app.state.store
                try:
                    store.update(job_id, status="running", stage="분석 시작")

                    async def stage(text):
                        store.update(job_id, stage=text)

                    if payload.mode == "demo":
                        for text in ("예제 상품 확인", "가상 리뷰 8건 · 사용 경험 2건 정리", "예제 리포트 작성"):
                            await stage(text)
                            await asyncio.sleep(.25)
                        report = demo_report()
                    else:
                        report = await asyncio.wait_for(live_runner(payload, settings, stage), settings.job_timeout_seconds)
                    store.update(job_id, status="completed", stage="분석 완료", report=report)
                except asyncio.CancelledError:
                    store.update(job_id, status="failed", stage="중단됨", error="서버 종료로 분석이 중단되었습니다. 다시 시도해 주세요.")
                    raise
                except Exception as exc:
                    # Never log response bodies, keys, prompts, or submitted purchase URLs.
                    logger.warning("Analysis failed job=%s type=%s", job_id, type(exc).__name__)
                    if isinstance(exc, AuthenticationError):
                        message = "분석 서비스 인증에 실패했습니다. 운영자는 API 키를 확인해 주세요."
                    elif isinstance(exc, RateLimitError):
                        message = "AI 서비스의 사용 한도 또는 호출량을 확인해 주세요. 잠시 후 다시 시도할 수 있습니다."
                    elif isinstance(exc, (TimeoutError, APIConnectionError)):
                        message = "분석 시간이 초과되었거나 외부 서비스에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요."
                    elif str(exc) == "local_model_unavailable":
                        message = "로컬 AI에 연결하지 못했습니다. Ollama를 실행하고 설정한 모델을 내려받아 주세요."
                    elif str(exc) == "naver_credentials_missing":
                        message = "네이버 공식 검색에는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 모두 필요합니다."
                    else:
                        message = "충분한 출처를 확보하지 못했거나 분석 응답을 검증하지 못했습니다. 상품명·링크와 서버 설정을 확인해 주세요."
                    store.update(job_id, status="failed", stage="분석 실패", error=message)
                finally:
                    app.state.queue.task_done()

        task = asyncio.create_task(worker())
        yield
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task

    app = FastAPI(title="리뷰렌즈 Agent API", version="1.0.0", lifespan=lifespan)

    @app.middleware("http")
    async def secure_headers(request: Request, call_next):
        if request.headers.get("content-length", "").isdigit() and int(request.headers["content-length"]) > 16384:
            return Response("Request too large", status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        if not request.url.path.startswith(("/docs", "/redoc")):
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    async def authorize(x_access_key: str = Header(default="")):
        if settings.app_access_key and not secrets.compare_digest(x_access_key, settings.app_access_key):
            raise HTTPException(401, "서비스 접근 키가 필요합니다. 설정에서 입력해 주세요.")

    @app.get("/healthz")
    async def health():
        return {"status": "ok"}

    @app.get("/api/config")
    async def config():
        ready = settings.live_enabled and (settings.ai_provider == "openai" or await local_ready(settings))
        if settings.use_naver and not (settings.naver_client_id and settings.naver_client_secret):
            ready = False
        return {"live_enabled": ready, "provider": settings.ai_provider, "model": settings.ollama_model if settings.ai_provider == "ollama" else settings.openai_model,
                "search_provider": "naver" if settings.use_naver else ("openai_web" if settings.ai_provider == "openai" and settings.search_provider == "auto" else "ddgs"),
                "access_key_required": bool(settings.app_access_key),
                "demo_product": {"product_name": DEMO_NAME, "product_url": DEMO_URL},
                "retention_days": settings.retention_days}

    @app.post("/api/analyses", status_code=202, dependencies=[Depends(authorize)])
    async def create_analysis(payload: AnalysisRequest):
        store = app.state.store
        store.cleanup(settings.retention_days)
        if payload.mode == "live" and settings.use_naver and not (settings.naver_client_id and settings.naver_client_secret):
            raise HTTPException(503, "네이버 공식 검색에는 NAVER_CLIENT_ID와 NAVER_CLIENT_SECRET이 모두 필요합니다.")
        if payload.mode == "live" and not settings.live_enabled:
            raise HTTPException(503, "분석 제공자 설정을 확인해 주세요. OpenAI 선택 시 OPENAI_API_KEY가 필요하며, 운영 환경에서는 24자 이상의 APP_ACCESS_KEY도 필요합니다.")
        if payload.mode == "live" and settings.ai_provider == "ollama" and not await local_ready(settings):
            raise HTTPException(503, "Ollama를 실행하고 설정한 모델을 내려받아 주세요. 로컬 AI에는 OpenAI API 키가 필요 없습니다.")
        if payload.mode == "live" and store.recent_live_count() >= settings.live_jobs_per_hour:
            raise HTTPException(429, "시간당 분석 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.")
        if store.recent_count() >= max(100, settings.live_jobs_per_hour):
            raise HTTPException(429, "서버의 시간당 요청 한도에 도달했습니다. 잠시 후 다시 시도해 주세요.")
        if app.state.queue.full():
            raise HTTPException(429, "분석 대기열이 가득 찼습니다. 잠시 후 다시 시도해 주세요.")
        if payload.mode == "demo":
            payload = AnalysisRequest(product_name=DEMO_NAME, product_url=DEMO_URL, mode="demo")
        job_id = str(uuid4())
        store.create(job_id, payload)
        app.state.queue.put_nowait((job_id, payload))
        return {"id": job_id, "status": "queued"}

    def get_job(job_id: UUID):
        app.state.store.cleanup(settings.retention_days)
        job = app.state.store.get(str(job_id))
        if job is None:
            raise HTTPException(404, "리포트를 찾을 수 없습니다. 삭제되었거나 보관 기간이 만료되었을 수 있습니다.")
        return job

    @app.get("/api/analyses/{job_id}", dependencies=[Depends(authorize)])
    async def read_analysis(job_id: UUID):
        return get_job(job_id)

    @app.get("/api/analyses/{job_id}/markdown", dependencies=[Depends(authorize)])
    async def export_analysis(job_id: UUID):
        job = get_job(job_id)
        if job["status"] != "completed":
            raise HTTPException(409, "분석이 완료된 뒤 내보낼 수 있습니다.")
        return Response(markdown_report(job["report"]), media_type="text/markdown",
                        headers={"Content-Disposition": 'attachment; filename="reviewlens-report.md"'})

    @app.delete("/api/analyses/{job_id}", status_code=204, dependencies=[Depends(authorize)])
    async def delete_analysis(job_id: UUID):
        if get_job(job_id)["status"] in {"queued", "running"}:
            raise HTTPException(409, "진행 중인 분석은 완료 후 삭제할 수 있습니다.")
        app.state.store.delete(str(job_id))
        return Response(status_code=204)

    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


app = create_app()
