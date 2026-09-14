import asyncio
from types import SimpleNamespace as NS

import httpx
import pytest

from app.agent import run_live
from app.collector import collect
from app.config import Settings
from app.export import markdown_report
from app.models import AnalysisRequest, EvidenceBundle, Narrative, Source
from app.naver import candidates
from tests.test_analysis import evidence


def settings(**kwargs):
    return Settings(_env_file=None, naver_client_id="test-id", naver_client_secret="test-secret", **kwargs)


async def stage(_):
    pass


def test_official_http_mapping_dedup_and_no_redirects(monkeypatch):
    original = httpx.AsyncClient
    seen = []

    def response(request):
        seen.append(request)
        kind = request.url.path.split("/")[-1]
        assert request.url.host == "naverapihub.apigw.ntruss.com"
        assert request.headers["X-NCP-APIGW-API-KEY"] == "test-secret"
        assert kind in {"blog", "webkr"}
        items = [{"title": "<b>Test</b> A1", "link": "https://example.com/review", "description": "<b>요약</b>입니다"},
                 {"title": "Bad link", "link": "http://127.0.0.1/a"}]
        return httpx.Response(200, json={"items": items})

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        return original(transport=httpx.MockTransport(response), **kwargs)

    monkeypatch.setattr("app.naver.httpx.AsyncClient", client)
    found, _ = asyncio.run(candidates(settings(), "Test A1"))
    assert len(seen) == 2
    assert len(found) == 1
    assert found["https://example.com/review"]["title"] == "Test A1"
    assert "전체 본문 아님" in found["https://example.com/review"]["body"]


@pytest.mark.parametrize("status", [401, 403, 429, 302])
def test_official_errors_do_not_follow_redirect_or_expose_secrets(monkeypatch, status):
    original = httpx.AsyncClient
    calls = []

    def response(request):
        calls.append(request)
        return httpx.Response(status, headers={"Location": "https://attacker.example.com"}, text="test-secret")

    monkeypatch.setattr("app.naver.httpx.AsyncClient", lambda **kw: original(transport=httpx.MockTransport(response), **kw))
    found, limitations = asyncio.run(candidates(settings(), "Test"))
    assert found == {}
    assert len(calls) == 2
    assert all(r.url.host == "naverapihub.apigw.ntruss.com" for r in calls)
    assert "test-secret" not in str(limitations)
    assert "검색 실패" in str(limitations)


def test_missing_credentials_fail_without_network():
    with pytest.raises(ValueError, match="naver_credentials_missing"):
        asyncio.run(candidates(Settings(_env_file=None, search_provider="naver"), "Test"))
    assert Settings(_env_file=None, naver_client_id="partial").use_naver


def test_official_collection_never_uses_ddgs_and_labels_snippets(monkeypatch):
    async def official(*args):
        return {"https://example.com/review": {"title": "Test", "body": "공식 검색 요약 데이터", "api_kind": "blog"}}, ["API 한계"]

    async def fetch(url):
        assert url in {"https://example.com/input", "https://example.com/review"}
        raise ValueError("blocked")

    def forbidden(*args):
        pytest.fail("Unofficial search must not be used")

    monkeypatch.setattr("app.naver.candidates", official)
    monkeypatch.setattr("app.collector.fetch_page", fetch)
    monkeypatch.setattr("app.collector.search", forbidden)
    _, records, limitations = asyncio.run(collect(
        AnalysisRequest(product_name="Test", product_url="https://example.com/input"), stage, settings()))
    assert len(records) == 1
    assert records[0]["api_kind"] == "blog"
    assert records[0]["has_page"] is False
    assert "API 한계" in limitations


@pytest.mark.parametrize("kind", ["blog", "webkr"])
@pytest.mark.parametrize("has_page", [False, True])
def test_official_openai_route_no_search_tools_and_snippet_cannot_be_review(monkeypatch, kind, has_page):
    calls = []
    item = evidence()

    async def collection(*args):
        return [Source(id="s1", title="Test", url="https://example.com/product")], [
            {"source_id": "s1", "url": "https://example.com/product", "text": item.passage,
             "api_kind": kind, "has_page": has_page}], []

    class Responses:
        async def parse(self, **kwargs):
            calls.append(kwargs)
            parsed = (EvidenceBundle(product_description="", evidence=[item], limitations=[])
                      if kwargs["text_format"] is EvidenceBundle else
                      Narrative(headline="표본 요약", summary="테스트", pros=[], cons=[], usage=[], suitable_for=[], consider_before_buying=[]))
            return NS(status="completed", output_parsed=parsed)

    class Client:
        def __init__(self, **kwargs):
            self.responses = Responses()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("app.local_agent.collect", collection)
    monkeypatch.setattr("app.local_agent.AsyncOpenAI", Client)
    result = asyncio.run(run_live(AnalysisRequest(product_name="Test", product_url="https://example.com/product"),
                                 settings(ai_provider="openai", openai_api_key="test"), stage))
    assert result["metrics"]["paired_count"] == int(has_page)
    assert len(calls) == (2 if has_page else 1)
    assert result["collection_provider"] == "naver"
    assert calls and all("tools" not in c and c["store"] is False for c in calls)
    assert "연구 메모 발췌" not in markdown_report(result)
