import json

import httpx
from openai import AsyncOpenAI
from pydantic import ValidationError

from app.agent import EXTRACTION_INSTRUCTIONS, SYNTHESIS_INSTRUCTIONS
from app.analysis import build_report, validate_evidence
from app.collector import collect
from app.models import EvidenceBundle, Narrative


async def local_ready(settings) -> bool:
    try:
        async with httpx.AsyncClient(timeout=2, trust_env=False) as client:
            response = await client.get(settings.ollama_base_url.rstrip("/") + "/api/tags")
            response.raise_for_status()
            return any(m.get("name") == settings.ollama_model for m in response.json().get("models", []))
    except (httpx.HTTPError, ValueError):
        return False


async def structured(settings, schema, instructions, data):
    if settings.ai_provider == "openai":
        async with AsyncOpenAI(api_key=settings.openai_api_key, timeout=90, max_retries=1) as client:
            response = await client.responses.parse(
                model=settings.openai_model, instructions=instructions,
                input=json.dumps(data, ensure_ascii=False), text_format=schema,
                max_output_tokens=5000, store=False,
            )
            if response.status != "completed" or response.output_parsed is None:
                raise ValueError("extraction_failed")
            return response.output_parsed
    async with httpx.AsyncClient(timeout=settings.job_timeout_seconds, trust_env=False) as client:
        prompt = instructions + "\n모든 설명과 요약을 한국어로 작성하세요. JSON 스키마를 정확히 따르세요.\n"
        response = await client.post(settings.ollama_base_url.rstrip("/") + "/api/chat", json={
            "model": settings.ollama_model, "stream": False,
            "format": schema.model_json_schema(),
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps(data, ensure_ascii=False)}],
            "options": {"temperature": 0, "num_ctx": 16384, "num_predict": 5000},
            "keep_alive": "10m",
        })
        response.raise_for_status()
        result = response.json()
        if result.get("done_reason") == "length":
            raise ValueError("Local model output truncated")
        return schema.model_validate_json(result["message"]["content"])


async def run_local(request, settings, stage):
    if settings.ai_provider == "ollama" and not await local_ready(settings):
        raise ValueError("local_model_unavailable")
    sources, records, limitations = await collect(request, stage, settings)
    label = "로컬 AI" if settings.ai_provider == "ollama" else "OpenAI"
    evidence, excluded = [], 0
    # Small batches keep the local model context bounded. Ground each batch to its own page.
    for index, record in enumerate(records[:6]):
        await stage(f"{label} · 상품 일치와 근거 추출 {index + 1}/{min(len(records), 6)}")
        source = next(s for s in sources if s.id == record["source_id"])
        try:
            bundle = await structured(settings, EvidenceBundle,
                                      EXTRACTION_INSTRUCTIONS + "\n자료는 인용 메모 대신 해당 source_id에서 직접 수집한 텍스트입니다. 한 페이지에서 최대 4개의 핵심 근거만 추출하세요. 검색 발췌만 있으면 개별 리뷰라고 단정하지 마세요.",
                                      {"product_name": request.product_name, "source": source.model_dump(), "memo": record["text"]})
            accepted, dropped = validate_evidence(bundle, [source], record["text"])
            if record.get("api_kind") and not record.get("has_page"):
                snippets = [item for item in accepted if item.kind != "review" and item.rating is None and not item.verified_purchase]
                dropped += len(accepted) - len(snippets)
                accepted = snippets
            excluded += dropped
            for item in accepted[:4]:
                item.id = f"e{len(evidence)+1}"
                evidence.append(item)
            limitations.extend(bundle.limitations[:2])
        except (ValidationError, KeyError, ValueError):
            limitations.append(f"{source.id}: AI의 추출 응답을 검증하지 못해 해당 자료를 제외했습니다.")
    if evidence:
        # Cross-page duplicate filtering after per-source validation and ID reassignment.
        combined = EvidenceBundle(product_description="", evidence=evidence, limitations=[])
        evidence, dropped = validate_evidence(combined, sources, "\n".join(r["text"] for r in records))
        excluded += dropped
        await stage(f"{label} · 장단점과 사용 경험 정리")
        narrative = await structured(settings, Narrative, SYNTHESIS_INSTRUCTIONS,
                                     {"product_name": request.product_name, "evidence": [e.model_dump() for e in evidence]})
    else:
        narrative = Narrative(headline="근거 부족", summary="공개 검색과 페이지에서 분석 가능한 근거를 충분히 확보하지 못했습니다.",
                              pros=[], cons=[], usage=[], suitable_for=[], consider_before_buying=[])
    limitations += [
        "검색 결과와 공개 페이지의 부분 자료를 AI로 분석했습니다. 전체 쇼핑몰 리뷰를 수집한 결과가 아닙니다.",
        "상품 일치·후기 유형·감성은 AI의 추정입니다. 검색 발췌는 원문 맥락이 부족할 수 있으므로 출처를 확인해 주세요.",
        "본문 감성 점수는 실제 구매자 평점이 아니며 구매 인증을 보장하지 않습니다.",
    ]
    if sum(e.rating is not None for e in evidence) < 10:
        limitations.append("별점과 본문이 있는 개별 리뷰가 10건 미만입니다. 괴리 지표를 일반화할 수 없습니다.")
    report = build_report(request, sources, evidence, narrative, limitations, excluded, "live")
    report["provider"] = settings.ai_provider
    report["model"] = settings.ollama_model if settings.ai_provider == "ollama" else settings.openai_model
    report["collection_provider"] = "naver" if settings.use_naver else "ddgs"
    report["evidence_origin"] = "collected"
    return report
