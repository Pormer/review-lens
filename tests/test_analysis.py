from app.analysis import metrics, validate_evidence, validate_narrative
from app.demo import demo_report
from app.models import Evidence, EvidenceBundle, Finding, Narrative, Source


def evidence(**updates):
    values = dict(id="e1", source_id="s1", kind="review", product_match="exact",
                  passage="소리는 좋지만 착용은 불편합니다. 별점 5점.", summary="착용감 아쉬움", aspect="착용감",
                  sentiment=-.5, rating=5, rating_evidence="별점 5점", verified_purchase=False, published_at=None)
    return Evidence(**(values | updates))


def test_pair_metrics_never_use_unrated_usage_or_aggregate():
    result = metrics([evidence(), evidence(id="e2", rating=None), evidence(id="e3", kind="usage", rating=4)])
    assert result["review_count"] == 2
    assert result["paired_count"] == 1
    assert result["average_rating"] == 5
    assert result["average_text_score"] == 2
    assert result["flagged_count"] == 1
    assert result["mismatch_percent"] is None


def test_no_evidence_means_no_numeric_claims():
    result = metrics([])
    assert result["average_rating"] is None
    assert result["average_text_score"] is None
    assert result["mismatch_percent"] is None
    assert result["source_count"] == 0


def test_mismatch_threshold_is_not_changed_by_display_rounding():
    assert metrics([evidence(sentiment=.2501)])["flagged_count"] == 0


def test_rejects_unknown_sources_variants_fabrication_and_duplicates():
    original = evidence()
    items = [original, evidence(id="e2"), evidence(id="e3", source_id="fabricated"),
             evidence(id="e4", product_match="variant"), evidence(id="e5", passage="연구 메모에 없는 완전히 만들어 낸 후기입니다.")]
    bundle = EvidenceBundle(product_description="test", evidence=items, limitations=[])
    accepted, excluded = validate_evidence(bundle, [Source(id="s1", title="Shop", url="https://example.com")], original.passage)
    assert [e.id for e in accepted] == ["e1"]
    assert excluded == 4


def test_rating_removed_without_own_rating_evidence():
    item = evidence(rating_evidence="쇼핑몰 평균 4.8")
    bundle = EvidenceBundle(product_description="test", evidence=[item], limitations=[])
    accepted, _ = validate_evidence(bundle, [Source(id="s1", title="Shop", url="https://example.com")], item.passage)
    assert accepted[0].rating is None


def test_findings_with_invalid_citation_are_removed():
    narrative = Narrative(headline="test", summary="test", pros=[Finding(title="bad", detail="bad", evidence_ids=["e1", "fake"])],
                          cons=[], usage=[], suitable_for=[], consider_before_buying=[])
    assert validate_narrative(narrative, [evidence()]).pros == []


def test_demo_is_explicit_and_internally_consistent():
    r = demo_report()
    assert r["mode"] == "demo"
    assert r["metrics"]["paired_count"] == 8
    assert r["metrics"]["average_rating"] == 4.38
    assert r["metrics"]["average_text_score"] == 3.41
    assert r["metrics"]["flagged_count"] == 3
    assert r["metrics"]["mismatch_percent"] == 38
    ids = {e["id"] for e in r["evidence"]}
    assert all(set(f["evidence_ids"]) <= ids for key in ("pros", "cons", "usage") for f in r["narrative"][key])
