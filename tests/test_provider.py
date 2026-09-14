import asyncio
from types import SimpleNamespace as NS

from app.agent import cited_sources, run_live
from app.config import Settings
from app.models import AnalysisRequest, EvidenceBundle, Narrative
from tests.test_analysis import evidence


def response_with_citation(url="https://example.com/review"):
    return NS(output=[NS(type="message", content=[NS(annotations=[NS(type="url_citation", url=url, title="Review")])])],
              status="completed", output_text=evidence().passage)


def test_only_safe_citation_sources_are_used():
    assert cited_sources(response_with_citation())[0].id == "s1"
    assert cited_sources(response_with_citation("javascript:alert(1)")) == []


def test_full_live_orchestration_with_mocked_provider(monkeypatch):
    calls = []
    bundle = EvidenceBundle(product_description="test", evidence=[evidence()], limitations=[])
    narrative = Narrative(headline="검증된 표본", summary="작은 표본입니다.", pros=[], cons=[], usage=[], suitable_for=[], consider_before_buying=[])

    class Responses:
        async def create(self, **kwargs):
            calls.append(kwargs)
            return response_with_citation()

        async def parse(self, **kwargs):
            calls.append(kwargs)
            return NS(status="completed", output_parsed=bundle if kwargs["text_format"] is EvidenceBundle else narrative)

    class Client:
        def __init__(self, **kwargs):
            self.responses = Responses()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    monkeypatch.setattr("app.agent.AsyncOpenAI", Client)
    stages = []

    async def stage(text):
        stages.append(text)

    report = asyncio.run(run_live(AnalysisRequest(product_name="테스트 모델", product_url="https://example.com/product"),
                                 Settings(_env_file=None, ai_provider="openai", openai_api_key="test"), stage))
    assert report["mode"] == "live"
    assert report["metrics"]["paired_count"] == 1
    assert len(stages) == 3
    assert len(calls) == 3
    assert all(c["store"] is False for c in calls)
    assert calls[0]["tool_choice"] == "required"
