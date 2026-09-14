import re
from collections import Counter
from statistics import mean

from app.models import Evidence, EvidenceBundle, Narrative, Source


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def validate_evidence(bundle: EvidenceBundle, sources: list[Source], memo: str) -> tuple[list[Evidence], int]:
    source_ids = {s.id for s in sources}
    accepted, seen, ids = [], set(), set()
    for item in bundle.evidence:
        fingerprint = re.sub(r"[\W_]+", "", item.passage).casefold()
        if (
            item.source_id not in source_ids or item.product_match != "exact"
            or normalize(item.passage) not in normalize(memo)
            or fingerprint in seen or item.id in ids
        ):
            continue
        # Ratings may only be attached to an individual review with explicit rating evidence.
        if (
            item.kind != "review" or not item.rating_evidence
            or normalize(item.rating_evidence) not in normalize(item.passage)
        ):
            item = item.model_copy(update={"rating": None, "rating_evidence": None})
        accepted.append(item)
        seen.add(fingerprint)
        ids.add(item.id)
    return accepted, len(bundle.evidence) - len(accepted)


def metrics(evidence: list[Evidence]) -> dict:
    reviews = [e for e in evidence if e.kind == "review"]
    paired = [e for e in reviews if e.rating is not None]
    # Sentiment proxy: -1 => 1, 0 => 3, +1 => 5; not a real consumer rating.
    gaps = [{"evidence_id": e.id, "rating": e.rating,
             "text_score": round(3 + 2 * e.sentiment, 2),
             "gap": round(e.rating - (3 + 2 * e.sentiment), 2),
             "is_mismatch": abs(e.rating - (3 + 2 * e.sentiment)) >= 1.5} for e in paired]
    flagged = [g for g in gaps if g["is_mismatch"]]
    return {
        "evidence_count": len(evidence), "review_count": len(reviews),
        "usage_count": sum(e.kind == "usage" for e in evidence),
        "source_count": len({e.source_id for e in evidence}),
        "paired_count": len(paired), "flagged_count": len(flagged),
        "average_rating": round(mean(e.rating for e in paired), 2) if paired else None,
        "average_text_score": round(mean(3 + 2 * e.sentiment for e in paired), 2) if paired else None,
        "mismatch_percent": round(100 * len(flagged) / len(paired)) if len(paired) >= 3 else None,
        "rating_distribution": {str(n): sum(round(e.rating) == n for e in paired) for n in range(1, 6)},
        "sentiment_distribution": dict(Counter(
            "positive" if e.sentiment > .2 else "negative" if e.sentiment < -.2 else "mixed" for e in reviews
        )),
        "gaps": gaps,
        "sample_label": "표본 부족" if len(paired) < 10 else "탐색적 표본",
        "method": "본문 감성(-1~1)을 3+2×감성으로 환산한 추정값과 별점을 비교합니다. 차이 절댓값이 1.5점 이상인 리뷰를 표시합니다. 구매자 평점이나 조작 판정이 아닙니다.",
    }


def validate_narrative(narrative: Narrative, evidence: list[Evidence]) -> Narrative:
    ids = {e.id for e in evidence}
    for field in ("pros", "cons", "usage"):
        # Drop claims with even one invalid citation rather than silently weakening their support.
        setattr(narrative, field, [f for f in getattr(narrative, field) if set(f.evidence_ids) <= ids])
    return narrative


def build_report(request, sources, evidence, narrative, limitations, excluded, mode):
    used = {e.source_id for e in evidence}
    limitations = list(dict.fromkeys(limitations))
    if not evidence:
        narrative = Narrative(
            headline="분석할 수 있는 근거를 충분히 찾지 못했습니다", summary="상품 모델명과 구매 링크를 확인한 뒤 다시 시도해 주세요.",
            pros=[], cons=[], usage=[], suitable_for=[], consider_before_buying=[])
    result = {
        "product_name": request.product_name, "product_url": request.product_url,
        "mode": mode, "narrative": validate_narrative(narrative, evidence).model_dump(),
        "metrics": metrics(evidence), "evidence": [e.model_dump() for e in evidence],
        "sources": [s.model_dump() for s in sources if s.id in used],
        "discovered_sources": [s.model_dump() for s in sources],
        "limitations": limitations, "excluded_count": excluded,
    }
    return result
