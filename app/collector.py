"""Bounded public web collection without API keys or access restriction bypasses."""
import asyncio
import ipaddress
import json
import socket
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup
from ddgs import DDGS

from app.models import Source, public_url

USER_AGENT = "ReviewLens/1.0 (+https://github.com/Pormer/review-lens)"


async def pinned_get(url: str, limit: int = 1_000_000):
    """Resolve once, reject every non-public address, connect to the validated IP with original TLS SNI.

    DNS re-resolution cannot redirect the connection into the local network. No proxy inheritance.
    Redirects are returned to the caller, not followed implicitly.
    """
    url = public_url(url)
    parsed = urlsplit(url)
    records = await asyncio.get_running_loop().getaddrinfo(
        parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(row[4][0] for row in records))
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("Non-public destination")
    target = httpx.URL(url).copy_with(host=addresses[0])
    async with httpx.AsyncClient(timeout=12, trust_env=False, follow_redirects=False) as client:
        async with client.stream("GET", target, headers={"Host": parsed.netloc, "User-Agent": USER_AGENT},
                                 extensions={"sni_hostname": parsed.hostname}) as response:
            data = bytearray()
            async for chunk in response.aiter_bytes():
                data.extend(chunk)
                if len(data) > limit:
                    raise ValueError("Page too large")
            return response.status_code, dict(response.headers), bytes(data)


async def allowed_by_robots(url: str) -> bool:
    parsed = urlsplit(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    try:
        status, _, body = await pinned_get(robots_url, limit=128_000)
        if status == 404:
            return True
        if status != 200:
            return False
        parser = RobotFileParser()
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        return parser.can_fetch(USER_AGENT, url)
    except (httpx.HTTPError, OSError, ValueError):
        return False


def extract_page(body: bytes) -> str:
    soup = BeautifulSoup(body, "html.parser")
    sections = []

    def visit(node):
        if isinstance(node, list):
            for child in node[:50]:
                visit(child)
        elif isinstance(node, dict):
            types = node.get("@type", [])
            types = [types] if isinstance(types, str) else types
            if "Product" in types:
                sections.append("상품 정보: " + str(node.get("name", "")) + " " + str(node.get("description", ""))[:1200])
                reviews = node.get("review", [])
                reviews = [reviews] if isinstance(reviews, dict) else reviews
                for review in reviews[:12] if isinstance(reviews, list) else []:
                    if not isinstance(review, dict) or not review.get("reviewBody"):
                        continue
                    rating = review.get("reviewRating", {})
                    rating = rating if isinstance(rating, dict) else {}
                    rating_text = f" 별점 {rating['ratingValue']}/{rating.get('bestRating', 5)}." if rating.get("ratingValue") else ""
                    sections.append("개별 리뷰: " + str(review["reviewBody"])[:700] + rating_text)
            if "@graph" in node:
                visit(node["@graph"])

    for tag in soup.find_all("script", type="application/ld+json")[:20]:
        try:
            visit(json.loads(tag.get_text()))
        except (ValueError, TypeError, RecursionError):
            continue
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript", "form"]):
        tag.decompose()
    content = soup.find("article") or soup.find("main") or soup.body or soup
    text = " ".join(content.stripped_strings)
    sections.append("페이지 본문: " + text[:6500])
    return "\n".join(sections)[:10000]


async def fetch_page(url: str) -> str:
    for _ in range(3):
        if not await allowed_by_robots(url):
            raise ValueError("robots/access policy prevents collection")
        status, headers, body = await pinned_get(url)
        if status in {301, 302, 303, 307, 308} and headers.get("location"):
            url = public_url(urljoin(url, headers["location"]))
            continue
        if status != 200 or "text/html" not in headers.get("content-type", ""):
            raise ValueError("Page unavailable or not HTML")
        return extract_page(body)
    raise ValueError("Too many redirects")


def search(query: str):
    # Explicit engine, not paid search APIs. Rate limits/errors remain visible to the caller.
    return DDGS(timeout=12).text(query, region="kr-kr", max_results=5, backend="google,brave,duckduckgo")


async def collect(request, stage, settings=None):
    host = urlsplit(request.product_url).hostname
    candidates = {request.product_url: {"title": request.product_name + " · 입력 구매 링크", "body": ""}}
    limitations = []
    if settings is not None and settings.use_naver:
        from app.naver import candidates as naver_candidates

        await stage("NAVER API HUB · 블로그·웹문서 검색")
        official, limitations = await naver_candidates(settings, request.product_name)
        candidates.update(official)
    else:
        await stage("무료 웹 검색 · 다른 쇼핑몰과 사용기 탐색")
    queries = [f'"{request.product_name}" site:{host}', f'"{request.product_name}" 구매 리뷰', f'"{request.product_name}" 사용 후기']
    for query in ([] if settings is not None and settings.use_naver else queries):
        try:
            results = await asyncio.wait_for(asyncio.to_thread(search, query), timeout=20)
            for item in results:
                try:
                    url = public_url(item.get("href", ""))
                except ValueError:
                    continue
                candidates.setdefault(url, {"title": item.get("title", url), "body": str(item.get("body", ""))[:1000]})
        except Exception:
            limitations.append("일부 무료 검색 요청이 제한되거나 결과를 반환하지 않았습니다.")
    sources, records = [], []
    await stage("공개 페이지 수집 · 접근 정책과 출처 확인")
    for index, (url, candidate) in enumerate(list(candidates.items())[:10]):
        has_page = False
        content = candidate["body"] if candidate.get("api_kind") else (
            "검색 발췌(전체 본문 아님): " + candidate["body"] if candidate["body"] else "")
        if index < 5:
            try:
                page = await asyncio.wait_for(fetch_page(url), timeout=25)
                content += "\n" + page
                has_page = True
            except Exception:
                limitations.append(f"{urlsplit(url).hostname}: 페이지 접근 또는 수집이 제한되어 원문을 확보하지 못했습니다.")
        if not content.strip():
            continue
        source = Source(id=f"s{len(sources)+1}", title=candidate["title"], url=url)
        sources.append(source)
        records.append({"source_id": source.id, "title": source.title, "url": url, "text": content[:10000],
                        "api_kind": candidate.get("api_kind"), "has_page": has_page})
    return sources, records, list(dict.fromkeys(limitations))
