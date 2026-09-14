from app.analysis import build_report
from app.models import AnalysisRequest, Evidence, Finding, Narrative, Source

DEMO_NAME = "오로라 사운드 A1 무선 헤드폰"
DEMO_URL = "https://example.com/products/aurora-a1"


def demo_report():
    request = AnalysisRequest(product_name=DEMO_NAME, product_url=DEMO_URL, mode="demo")
    sources = [Source(id=f"s{i}", title=title, url=f"https://example.com/demo/{i}") for i, title in enumerate(
        ["예제 쇼핑몰 A · 구매 리뷰", "예제 쇼핑몰 B · 구매 리뷰", "예제 블로그 · 30일 사용기"], 1)]
    rows = [
        ("s1", "review", "출퇴근 지하철에서 소음이 줄어 음악에 집중하기 좋아요. 별점 5점.", "지하철에서 유용한 소음 차단", "소음 차단", .9, 5),
        ("s1", "review", "음질은 만족하지만 두 시간 정도 쓰면 정수리가 눌립니다. 별점 5점.", "긴 착용 시간에는 압박감", "착용감", -.25, 5),
        ("s1", "review", "충전 한 번으로 사흘 출퇴근했어요. 배터리는 만족합니다. 별점 5점.", "일상 사용에서 충분한 배터리", "배터리", .8, 5),
        ("s1", "review", "소리는 괜찮은데 바람 부는 곳에서 통화가 어렵네요. 별점 4점.", "야외 통화 시 바람 소리", "통화 품질", -.6, 4),
        ("s2", "review", "노트북과 휴대폰 전환이 간단해 업무할 때 편합니다. 별점 5점.", "두 기기 사이의 편리한 전환", "연결성", .8, 5),
        ("s2", "review", "저음이 선명하고 소음 차단도 마음에 들어요. 별점 4점.", "음질과 소음 차단에 만족", "음질", .75, 4),
        ("s2", "review", "안경을 쓰면 귀 주변이 눌려서 오래 쓰기 불편했어요. 별점 3점.", "안경 착용 시 압박감", "착용감", -.75, 3),
        ("s2", "review", "버튼은 편하지만 접히지 않아 가방 공간을 차지합니다. 별점 4점.", "조작은 편리하지만 휴대 부피가 큼", "휴대성", .0, 4),
        ("s3", "usage", "한 달 사용하면서 실내 통화는 무난했지만 야외에서는 바람 소리가 전달됐다.", "야외 통화가 잦으면 별도 확인 필요", "통화 품질", -.4, None),
        ("s3", "usage", "퇴근 후 두 시간씩 착용할 때 중간에 한 번씩 벗어 주면 압박감이 줄었다.", "장시간 사용 중에는 휴식 권장", "착용감", -.2, None),
    ]
    evidence = [Evidence(id=f"e{i}", source_id=s, kind=kind, product_match="exact", passage=text,
                         summary=summary, aspect=aspect, sentiment=sentiment, rating=rating,
                         rating_evidence=f"별점 {rating}점" if rating else None,
                         verified_purchase=False, published_at=None)
                for i, (s, kind, text, summary, aspect, sentiment, rating) in enumerate(rows, 1)]
    narrative = Narrative(
        headline="출퇴근의 소음은 줄이고, 오래 쓸 때의 착용감은 확인하세요.",
        summary="예제 후기에서는 소음 차단과 배터리가 장점으로 나타났습니다. 다만 높은 별점을 준 리뷰에도 착용 압박과 야외 통화에 대한 불만이 포함되어 있습니다. 별점만 보기보다 사용 환경과 착용 시간을 함께 고려해 보세요.",
        pros=[Finding(title="출퇴근에 유용한 소음 차단", detail="지하철 소음을 줄여 음악에 집중하기 좋다는 평가가 있습니다.", evidence_ids=["e1", "e6"]),
              Finding(title="넉넉한 배터리와 간편한 기기 전환", detail="출퇴근 사용 시 배터리에 만족했고, 노트북과 휴대폰을 함께 사용하는 상황에 편리했습니다.", evidence_ids=["e3", "e5"])],
        cons=[Finding(title="장시간 착용 시 압박감", detail="정수리와 안경 주변이 눌린다는 후기가 있어 구매 전 착용 확인을 권합니다.", evidence_ids=["e2", "e7"]),
              Finding(title="바람 부는 곳에서 아쉬운 통화", detail="야외 통화에서 바람 소리가 전달된다는 구매 후기와 사용기가 있습니다.", evidence_ids=["e4", "e9"])],
        usage=[Finding(title="두 시간 이상 쓸 때는 잠깐의 휴식", detail="장시간 연속 착용할 때 중간에 벗어 주면 압박감을 덜 수 있다는 사용 경험입니다.", evidence_ids=["e10"]),
               Finding(title="야외 통화가 많다면 먼저 테스트", detail="음악 감상과 통화 품질은 별도로 판단하는 것이 좋습니다.", evidence_ids=["e9"])],
        suitable_for=["지하철로 출퇴근하며 음악을 듣는 분", "휴대폰과 노트북을 번갈아 사용하는 분"],
        consider_before_buying=["안경을 쓴 상태에서 착용해 보기", "야외 통화 품질과 가방 수납 공간 확인하기"])
    return build_report(request, sources, evidence, narrative,
                        ["이 상품·쇼핑몰·후기·수치는 기능 시연을 위해 만든 가상 데이터입니다. 실제 구매 판단에 사용하지 마세요.",
                         "별점과 본문이 있는 예제 리뷰는 8건입니다. 전체 구매자의 의견을 대표하지 않습니다."], 0, "demo")
