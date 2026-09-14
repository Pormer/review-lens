import asyncio
import socket

import pytest

from app.collector import extract_page, pinned_get
from app.config import Settings
from app.local_agent import run_local
from app.models import AnalysisRequest, EvidenceBundle, Narrative, Source
from tests.test_analysis import evidence


def test_local_is_default_and_never_requires_openai_key():
    settings = Settings(_env_file=None, openai_api_key="")
    assert settings.ai_provider == "ollama"
    assert settings.live_enabled


def test_structured_page_reviews_do_not_inherit_aggregate_rating():
    html = b'''<html><script type="application/ld+json">{"@type":"Product","name":"Test A1",
    "aggregateRating":{"ratingValue":4.9},"review":[{"reviewBody":"Good sound","reviewRating":{"ratingValue":3}}]}</script>
    <body><nav>ignore nav</nav><main>Public product text</main></body></html>'''
    result = extract_page(html)
    assert "Good sound" in result
    assert "3/5" in result
    assert "4.9" not in result
    assert "ignore nav" not in result


def test_fetch_rejects_dns_resolving_to_private_address(monkeypatch):
    async def test():
        async def fake_dns(*args, **kwargs):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_dns)
        with pytest.raises(ValueError, match="Non-public"):
            await pinned_get("https://attacker.example.com")
    asyncio.run(test())


def test_local_pipeline_with_mock_model_and_collector(monkeypatch):
    item = evidence()
    source = Source(id="s1", title="Test", url="https://example.com")

    async def ready(settings):
        return True

    async def collection(*args):
        return [source], [{"source_id": "s1", "text": item.passage}], []

    async def model(settings, schema, instructions, data):
        if schema is EvidenceBundle:
            return EvidenceBundle(product_description="Test", evidence=[item], limitations=[])
        return Narrative(headline="표본 분석", summary="테스트 요약", pros=[], cons=[], usage=[], suitable_for=[], consider_before_buying=[])

    async def stage(text):
        pass

    monkeypatch.setattr("app.local_agent.local_ready", ready)
    monkeypatch.setattr("app.local_agent.collect", collection)
    monkeypatch.setattr("app.local_agent.structured", model)
    report = asyncio.run(run_local(AnalysisRequest(product_name="테스트 모델", product_url="https://example.com"), Settings(_env_file=None), stage))
    assert report["provider"] == "ollama"
    assert report["metrics"]["paired_count"] == 1
