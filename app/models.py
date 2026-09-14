import ipaddress
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


def public_url(value: str) -> str:
    """Validate links only; the application never fetches arbitrary user URLs itself."""
    value = value.strip()
    if len(value) > 2048 or any(ord(c) < 33 for c in value):
        raise ValueError("공백 없는 올바른 구매 링크를 입력해 주세요.")
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            raise ValueError()
        if parsed.port not in {None, 80, 443} or "." not in host or host.endswith((".local", ".localhost", ".internal")):
            raise ValueError()
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            ip = None
        if ip is not None or host == "localhost":
            raise ValueError()
    except ValueError:
        raise ValueError("공개 쇼핑몰의 http 또는 https 상품 링크를 입력해 주세요.") from None
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    product_name: str = Field(min_length=2, max_length=160)
    product_url: str = Field(max_length=2048)
    mode: Literal["live", "demo"] = "live"

    @field_validator("product_name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2 or any(ord(c) < 32 for c in value):
            raise ValueError("정확한 상품명을 두 글자 이상 입력해 주세요.")
        return value

    @field_validator("product_url")
    @classmethod
    def clean_url(cls, value: str) -> str:
        return public_url(value)


class Source(BaseModel):
    id: str
    title: str
    url: str


class Evidence(BaseModel):
    id: str
    source_id: str
    kind: Literal["review", "usage", "spec"]
    product_match: Literal["exact", "variant", "unknown"]
    # A short verbatim span of the research memo, not a claimed original review quote.
    passage: str = Field(min_length=8, max_length=600)
    summary: str = Field(min_length=1, max_length=350)
    aspect: str = Field(max_length=40)
    sentiment: float = Field(ge=-1, le=1)
    rating: float | None = Field(ge=1, le=5)
    rating_evidence: str | None
    verified_purchase: bool
    published_at: str | None


class EvidenceBundle(BaseModel):
    product_description: str
    evidence: list[Evidence] = Field(max_length=40)
    limitations: list[str] = Field(max_length=12)


class Finding(BaseModel):
    title: str = Field(max_length=90)
    detail: str = Field(max_length=500)
    evidence_ids: list[str] = Field(min_length=1, max_length=10)


class Narrative(BaseModel):
    headline: str = Field(max_length=160)
    summary: str = Field(max_length=800)
    pros: list[Finding] = Field(max_length=5)
    cons: list[Finding] = Field(max_length=5)
    usage: list[Finding] = Field(max_length=5)
    suitable_for: list[str] = Field(max_length=4)
    consider_before_buying: list[str] = Field(max_length=4)
