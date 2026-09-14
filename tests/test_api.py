import time
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.demo import DEMO_NAME, DEMO_URL, demo_report
from app.main import create_app
from app.models import AnalysisRequest
from app.storage import Store


def settings(tmp_path, **overrides):
    return Settings(_env_file=None, database_path=str(tmp_path / "test.db"), openai_api_key="", app_access_key="", ai_provider="openai", **overrides)


def payload(mode="demo", **updates):
    return {"product_name": "소니 WH-1000XM5", "product_url": "https://www.coupang.com/vp/products/123", "mode": mode} | updates


def await_job(client, job_id, headers=None):
    for _ in range(100):
        result = client.get(f"/api/analyses/{job_id}", headers=headers).json()
        if result["status"] in {"completed", "failed"}:
            return result
        time.sleep(.03)
    pytest.fail("Job did not finish")


def test_demo_end_to_end_export_delete(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.get("/healthz").json() == {"status": "ok"}
        assert client.get("/").status_code == 200
        assert client.get("/static/app.js").status_code == 200
        assert not client.get("/api/config").json()["live_enabled"]
        created = client.post("/api/analyses", json=payload())
        assert created.status_code == 202
        job_id = created.json()["id"]
        job = await_job(client, job_id)
        assert job["status"] == "completed"
        assert job["request"]["product_name"] == DEMO_NAME
        assert job["report"]["product_url"] == DEMO_URL
        exported = client.get(f"/api/analyses/{job_id}/markdown")
        assert exported.status_code == 200
        assert "가상 예제" in exported.text
        assert "e1" in exported.text
        assert client.delete(f"/api/analyses/{job_id}").status_code == 204
        assert client.get(f"/api/analyses/{job_id}").status_code == 404


@pytest.mark.parametrize("url", ["file:///etc/passwd", "javascript:alert(1)", "https://127.0.0.1/", "https://localhost/", "https://192.168.0.1/", "https://user:pass@example.com", "https://service.local", "https://example.com:444", "https://example.com/a b"])
def test_invalid_urls_rejected(tmp_path, url):
    with TestClient(create_app(settings(tmp_path))) as client:
        assert client.post("/api/analyses", json=payload(product_url=url)).status_code == 422


def test_live_without_key_never_silently_falls_back_to_demo(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.post("/api/analyses", json=payload("live"))
        assert response.status_code == 503
        assert "OPENAI_API_KEY" in response.json()["detail"]


def test_access_key_protects_create_read_and_export(tmp_path):
    cfg = settings(tmp_path)
    cfg.app_access_key = "long-service-key"
    with TestClient(create_app(cfg)) as client:
        assert client.post("/api/analyses", json=payload()).status_code == 401
        assert client.get(f"/api/analyses/{uuid4()}").status_code == 401
        headers = {"X-Access-Key": cfg.app_access_key}
        created = client.post("/api/analyses", json=payload(), headers=headers)
        assert created.status_code == 202
        job = await_job(client, created.json()["id"], headers)
        assert client.get(f"/api/analyses/{job['id']}/markdown").status_code == 401


def test_production_live_requires_strong_service_key(tmp_path):
    cfg = settings(tmp_path, app_env="production")
    cfg.openai_api_key = "test-key"
    assert not cfg.live_enabled
    cfg.app_access_key = "a" * 24
    assert cfg.live_enabled


def test_live_worker_failure_is_safe_and_persisted(tmp_path):
    async def failing_runner(*args):
        raise RuntimeError("secret-provider-response")

    cfg = settings(tmp_path)
    cfg.openai_api_key = "test-key"
    with TestClient(create_app(cfg, live_runner=failing_runner)) as client:
        created = client.post("/api/analyses", json=payload("live"))
        job = await_job(client, created.json()["id"])
        assert job["status"] == "failed"
        assert "secret" not in job["error"]
        assert job["report"] is None


def test_live_limit_counts_prior_calls(tmp_path):
    async def fake_runner(*args):
        return demo_report()

    cfg = settings(tmp_path, live_jobs_per_hour=1)
    cfg.openai_api_key = "test-key"
    with TestClient(create_app(cfg, live_runner=fake_runner)) as client:
        created = client.post("/api/analyses", json=payload("live"))
        await_job(client, created.json()["id"])
        client.delete(f"/api/analyses/{created.json()['id']}")
        assert client.post("/api/analyses", json=payload("live")).status_code == 429


def test_recovery_marks_interrupted_jobs_failed(tmp_path):
    cfg = settings(tmp_path)
    store = Store(cfg.database_path)
    job_id = str(uuid4())
    store.create(job_id, AnalysisRequest(**payload()))
    with TestClient(create_app(cfg)) as client:
        job = client.get(f"/api/analyses/{job_id}").json()
        assert job["status"] == "failed"
        assert "재시작" in job["error"]


def test_unknown_job_and_security_headers(tmp_path):
    with TestClient(create_app(settings(tmp_path))) as client:
        response = client.get(f"/api/analyses/{uuid4()}")
        assert response.status_code == 404
        assert response.headers["cache-control"] == "no-store"
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert client.get("/api/analyses/not-an-id").status_code == 422


def test_queue_capacity_and_in_progress_delete(tmp_path):
    import asyncio

    async def waiting_runner(*args):
        await asyncio.sleep(30)

    cfg = settings(tmp_path, max_pending_jobs=1)
    cfg.openai_api_key = "test-key"
    with TestClient(create_app(cfg, live_runner=waiting_runner)) as client:
        first = client.post("/api/analyses", json=payload("live"))
        time.sleep(.05)
        second = client.post("/api/analyses", json=payload("live"))
        assert second.status_code == 202
        assert client.post("/api/analyses", json=payload("live")).status_code == 429
        assert client.delete(f"/api/analyses/{first.json()['id']}").status_code == 409
