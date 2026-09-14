import asyncio

from app.analysis import build_report
from app.collector import collect, extract_page, search
from app.models import AnalysisRequest, Narrative, Source


def test_search_excludes_ad_links_and_uses_korean_language(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            pass

        def text(self, query, **kwargs):
            assert kwargs["region"] == "kr-ko"
            assert "bing" in kwargs["backend"]
            return [{"href": "https://www.bing.com/aclick?tracking=1"},
                    {"href": "https://example.com/review", "title": "Review", "body": "Text"}]

    monkeypatch.setattr("app.collector.DDGS", Client)
    assert [r["href"] for r in search("Model 8")] == ["https://example.com/review"]


def test_collection_recovers_when_exact_store_query_and_purchase_page_fail(monkeypatch):
    queries = []

    def lookup(query):
        queries.append(query)
        if "site:" in query:
            raise ValueError("No results")
        assert '"' not in query
        return [{"href": "https://example.com/review", "title": "Model 8 review", "body": "Search snippet"}]

    async def fetch(url):
        if url.endswith("/purchase"):
            raise ValueError("Access blocked")
        return "페이지 본문: Model 8 has a bright screen and lasted all day."

    async def stage(text):
        pass

    monkeypatch.setattr("app.collector.search", lookup)
    monkeypatch.setattr("app.collector.fetch_page", fetch)
    sources, records, limitations = asyncio.run(collect(
        AnalysisRequest(product_name="Model 8", product_url="https://example.com/purchase"), stage))
    assert len(queries) == 3
    assert len(sources) == len(records) == 1
    assert records[0]["has_page"] is True
    assert "bright screen" in records[0]["text"]
    assert limitations


def test_empty_html_is_not_readable_page():
    assert extract_page(b"<html><body><script>loading()</script></body></html>") == ""


def test_empty_report_distinguishes_collection_failure_from_rejected_evidence():
    request = AnalysisRequest(product_name="Model 8", product_url="https://example.com/product")
    narrative = Narrative(headline="", summary="", pros=[], cons=[], usage=[], suitable_for=[], consider_before_buying=[])
    missing = build_report(request, [], [], narrative, [], 0, "live")
    rejected = build_report(request, [Source(id="s1", title="Review", url="https://example.com/review")],
                            [], narrative, [], 2, "live")
    assert "가져오지 못했습니다" in missing["narrative"]["summary"]
    assert "검증을 통과한 근거가 없습니다" in rejected["narrative"]["summary"]
    assert missing["metrics"]["average_rating"] is None
    assert rejected["metrics"]["average_rating"] is None
