"""Official Search API adapter. Search metadata is never an individual review."""
import asyncio

import httpx
from bs4 import BeautifulSoup

from app.models import public_url


def plain(value, limit=1000):
    return BeautifulSoup(str(value or "")[:5000], "html.parser").get_text(" ", strip=True)[:limit]


async def search_api(client, kind, query):
    if kind not in {"blog", "webkr"}:
        raise ValueError("Invalid search kind")
    response = await client.get(f"https://naverapihub.apigw.ntruss.com/search/v1/{kind}",
                                params={"query": query, "display": 3, "start": 1, "format": "json"})
    # Never follow redirects carrying client credentials to another host.
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise ValueError("Invalid search response")
    return data["items"][:3]


async def candidates(settings, product_name):
    if not settings.naver_client_id or not settings.naver_client_secret:
        raise ValueError("naver_credentials_missing")
    headers = {"X-NCP-APIGW-API-KEY-ID": settings.naver_client_id,
               "X-NCP-APIGW-API-KEY": settings.naver_client_secret}
    queries = [("blog", product_name + " 사용 후기"),
               ("webkr", product_name + " 구매 리뷰")]
    async with httpx.AsyncClient(headers=headers, timeout=12, trust_env=False, follow_redirects=False) as client:
        results = await asyncio.gather(*(search_api(client, kind, query) for kind, query in queries),
                                       return_exceptions=True)
    found, limitations = {}, [
        "NAVER API HUB의 블로그·웹문서 검색 결과입니다. 동일 상품 여부는 별도 검증이 필요합니다.",
        "API 검색 요약은 원문 전체나 개별 구매 리뷰·별점 데이터가 아닙니다.",
        "네이버 쇼핑 검색 API는 종료되어 사용하지 않습니다. 상품 정보는 접근 가능한 공개 페이지에서 확인합니다.",
    ]
    groups = []
    for (kind, _), result in zip(queries, results, strict=True):
        group = []
        if isinstance(result, Exception):
            status = result.response.status_code if isinstance(result, httpx.HTTPStatusError) else None
            reason = {401: "인증 실패", 403: "권한 없음", 429: "호출 한도 초과"}.get(status, "응답 오류")
            limitations.append(f"네이버 {kind} 검색 실패: {reason}. 유료 검색으로 전환하지 않았습니다.")
        else:
            for item in result:
                if not isinstance(item, dict):
                    continue
                try:
                    url = public_url(str(item.get("link", "")))
                except ValueError:
                    continue
                title = plain(item.get("title"), 300)
                body = f"NAVER API HUB {kind} 검색 요약(전체 본문 아님): " + plain(item.get("description"))
                group.append((url, {"title": title or url, "body": body, "api_kind": kind}))
        groups.append(group)
    # Interleave source types so a small AI context budget still sees usage evidence.
    for index in range(3):
        for group in groups:
            if index < len(group):
                url, candidate = group[index]
                found.setdefault(url, candidate)
    return found, limitations
