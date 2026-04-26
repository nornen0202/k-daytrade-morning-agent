from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from importlib import import_module
from xml.etree import ElementTree

import requests

from daytrade_agent.collectors.base import CollectorResult, insufficient_result
from daytrade_agent.config import AppConfig
from daytrade_agent.normalizers.event_schema import MarketEvent, Source, parse_datetime, stable_id

_NAVER_ENDPOINT = "https://openapi.naver.com/v1/search/news.json"
_NEWSAPI_ENDPOINT = "https://newsapi.org/v2/everything"
_ALPHA_VANTAGE_ENDPOINT = "https://www.alphavantage.co/query"
_PUBLIC_REPLACEMENTS = {
    "무조건 매수": "매수 강요 표현",
    "확실한 수익": "수익 보장성 표현",
    "상한가 확정": "가격 급등 확정 표현",
    "작전주": "근거 부족 테마",
    "세력주": "수급 집중 관련 표현",
    "조작": "보도 기준 의혹",
    "계좌": "금융계정 관련 표현",
    "보유비중": "비중 정보",
}


def collect_news_category(
    config: AppConfig,
    category: str,
    collected_at: datetime,
) -> CollectorResult:
    results: list[CollectorResult] = []
    failure_reasons: list[str] = []

    for provider in _provider_priority(config):
        try:
            result = _collect_provider(provider, category, collected_at, config)
        except Exception as exc:
            failure_reasons.append(f"{provider} failed: {type(exc).__name__}")
            continue
        if result.events:
            results.append(result)
        elif result.missing_data:
            failure_reasons.extend(result.missing_data)

    merged = _merge_results(results)
    if merged.events:
        return merged

    reason = "; ".join(failure_reasons) if failure_reasons else "no news provider configured"
    return insufficient_result(category, reason)


def _collect_provider(
    provider: str,
    category: str,
    collected_at: datetime,
    config: AppConfig,
) -> CollectorResult:
    if provider == "rss":
        rss_urls = _rss_urls(config)
        if not rss_urls:
            return CollectorResult()
        return _collect_rss(category, rss_urls, collected_at)
    if provider == "naver":
        if not (config.env("NAVER_CLIENT_ID") and config.env("NAVER_CLIENT_SECRET")):
            return CollectorResult()
        return _collect_naver(category, _queries(config, category), collected_at, config)
    if provider == "newsapi":
        if not config.env("NEWS_API_KEY"):
            return CollectorResult()
        return _collect_newsapi(category, _queries(config, category), collected_at, config)
    if provider == "alpha_vantage":
        if not config.env("ALPHA_VANTAGE_API_KEY"):
            return CollectorResult()
        return _collect_alpha_vantage(category, collected_at, config)
    if provider == "yfinance":
        return _collect_yfinance(category, collected_at, config)
    return CollectorResult()


def _collect_rss(category: str, rss_urls: list[str], collected_at: datetime) -> CollectorResult:
    events: list[MarketEvent] = []
    sources: list[Source] = []
    for url in rss_urls:
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        root = ElementTree.fromstring(response.text)
        for item in root.findall(".//item")[:10]:
            event, source = _event_and_source(
                category=category,
                provider="rss",
                title=_strip_html(item.findtext("title") or "데이터 부족"),
                summary=_strip_html(item.findtext("description") or "데이터 부족"),
                url=item.findtext("link") or url,
                published=parse_datetime(item.findtext("pubDate")),
                collected_at=collected_at,
                source_quality=0.55,
            )
            events.append(event)
            sources.append(source)
    return CollectorResult(events=events, sources=sources)


def _collect_naver(
    category: str,
    queries: list[str],
    collected_at: datetime,
    config: AppConfig,
) -> CollectorResult:
    headers = {
        "X-Naver-Client-Id": config.env("NAVER_CLIENT_ID") or "",
        "X-Naver-Client-Secret": config.env("NAVER_CLIENT_SECRET") or "",
    }
    endpoint = str(config.data_sources.get("news", {}).get("naver_endpoint") or _NAVER_ENDPOINT)
    events: list[MarketEvent] = []
    sources: list[Source] = []
    for query in queries:
        response = requests.get(
            endpoint,
            headers=headers,
            params={"query": query, "display": 10, "sort": "date"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("items", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            event, source = _event_and_source(
                category=category,
                provider="Naver News",
                title=_strip_html(str(item.get("title") or "데이터 부족")),
                summary=_strip_html(str(item.get("description") or "데이터 부족")),
                url=str(item.get("originallink") or item.get("link") or ""),
                published=_parse_pubdate(item.get("pubDate")),
                collected_at=collected_at,
                source_quality=0.65,
            )
            events.append(event)
            sources.append(source)
    return _dedupe_result(events, sources)


def _collect_newsapi(
    category: str,
    queries: list[str],
    collected_at: datetime,
    config: AppConfig,
) -> CollectorResult:
    endpoint = str(config.data_sources.get("news", {}).get("newsapi_endpoint") or _NEWSAPI_ENDPOINT)
    headers = {"X-Api-Key": config.env("NEWS_API_KEY") or ""}
    events: list[MarketEvent] = []
    sources: list[Source] = []
    for query in queries:
        response = requests.get(
            endpoint,
            headers=headers,
            params={"q": query, "pageSize": 10, "sortBy": "publishedAt", "language": "ko"},
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        for item in payload.get("articles", []) if isinstance(payload, dict) else []:
            if not isinstance(item, dict):
                continue
            source_payload = item.get("source") if isinstance(item.get("source"), dict) else {}
            event, source = _event_and_source(
                category=category,
                provider=str(source_payload.get("name") or "NewsAPI"),
                title=_strip_html(str(item.get("title") or "데이터 부족")),
                summary=_strip_html(str(item.get("description") or "데이터 부족")),
                url=str(item.get("url") or ""),
                published=parse_datetime(item.get("publishedAt")),
                collected_at=collected_at,
                source_quality=0.55,
            )
            events.append(event)
            sources.append(source)
    return _dedupe_result(events, sources)


def _collect_alpha_vantage(
    category: str,
    collected_at: datetime,
    config: AppConfig,
) -> CollectorResult:
    endpoint = str(
        config.data_sources.get("news", {}).get("alpha_vantage_endpoint")
        or _ALPHA_VANTAGE_ENDPOINT
    )
    response = requests.get(
        endpoint,
        params={
            "function": "NEWS_SENTIMENT",
            "topics": _alpha_topics(category),
            "sort": "LATEST",
            "limit": "20",
            "apikey": config.env("ALPHA_VANTAGE_API_KEY") or "",
        },
        timeout=20,
    )
    response.raise_for_status()
    payload = response.json()
    feed = payload.get("feed", []) if isinstance(payload, dict) else []
    events: list[MarketEvent] = []
    sources: list[Source] = []
    for item in feed:
        if not isinstance(item, dict):
            continue
        event, source = _event_and_source(
            category=category,
            provider=str(item.get("source") or "Alpha Vantage"),
            title=_strip_html(str(item.get("title") or "데이터 부족")),
            summary=_strip_html(str(item.get("summary") or "데이터 부족")),
            url=str(item.get("url") or ""),
            published=_parse_alpha_datetime(item.get("time_published")),
            collected_at=collected_at,
            source_quality=0.58,
            candidate_symbols=_alpha_symbols(item),
        )
        events.append(event)
        sources.append(source)
    return _dedupe_result(events, sources)


def _collect_yfinance(
    category: str,
    collected_at: datetime,
    config: AppConfig,
) -> CollectorResult:
    try:
        yf = import_module("yfinance")
    except ImportError:
        return CollectorResult()

    events: list[MarketEvent] = []
    sources: list[Source] = []
    for ticker in _yfinance_tickers(config, category):
        news = yf.Ticker(ticker).get_news(count=8)
        for item in news or []:
            if not isinstance(item, dict):
                continue
            fields = _yfinance_article_fields(item)
            event, source = _event_and_source(
                category=category,
                provider=fields["provider"],
                title=_strip_html(fields["title"]),
                summary=_strip_html(fields["summary"]),
                url=fields["url"],
                published=fields["published"],
                collected_at=collected_at,
                source_quality=0.45,
                candidate_symbols=[_krx_symbol_from_yahoo(ticker)],
            )
            events.append(event)
            sources.append(source)
    return _dedupe_result(events, sources)


def _event_and_source(
    *,
    category: str,
    provider: str,
    title: str,
    summary: str,
    url: str,
    published: datetime | None,
    collected_at: datetime,
    source_quality: float,
    candidate_symbols: list[str] | None = None,
) -> tuple[MarketEvent, Source]:
    source_id = stable_id("src", provider, url, title)
    source_url = url if url.startswith(("http://", "https://")) else None
    event = MarketEvent(
        event_id=stable_id("evt", category, source_id, title),
        category=category,
        title=title,
        summary=summary,
        published_at=published,
        source_id=source_id,
        source_url=source_url,
        source_name=provider,
        source_quality=source_quality,
        affected_sectors=_affected_sectors(title, summary),
        candidate_symbols=[symbol for symbol in candidate_symbols or [] if symbol],
        confidence=0.5,
        data_status="partial",
    )
    source = Source(
        source_id=source_id,
        source_name=provider,
        source_url=source_url,
        source_type=category,
        published_at=published,
        collected_at=collected_at,
        source_quality=source_quality,
    )
    return event, source


def _merge_results(results: list[CollectorResult]) -> CollectorResult:
    events: list[MarketEvent] = []
    sources: list[Source] = []
    for result in results:
        events.extend(result.events)
        sources.extend(result.sources)
    return _dedupe_result(events, sources)


def _dedupe_result(events: list[MarketEvent], sources: list[Source]) -> CollectorResult:
    by_event_id = {event.event_id: event for event in events}
    by_source_id = {source.source_id: source for source in sources}
    return CollectorResult(events=list(by_event_id.values()), sources=list(by_source_id.values()))


def _provider_priority(config: AppConfig) -> list[str]:
    news_config = config.data_sources.get("news", {})
    raw_priority = news_config.get("provider_priority", []) if isinstance(news_config, dict) else []
    priority = [str(provider).strip() for provider in raw_priority if str(provider).strip()]
    return priority or ["rss", "naver", "newsapi", "alpha_vantage", "yfinance"]


def _queries(config: AppConfig, category: str) -> list[str]:
    news_config = config.data_sources.get("news", {})
    query_map = news_config.get("query_map", {}) if isinstance(news_config, dict) else {}
    raw_queries = query_map.get(category, []) if isinstance(query_map, dict) else []
    if isinstance(raw_queries, list):
        queries = [str(query).strip() for query in raw_queries if str(query).strip()]
    else:
        queries = []
    fallback = {
        "political_theme": ["한국 정책 주식", "정부 산업 정책 증시"],
        "global_issue": ["미국 증시 금리 환율 반도체", "중국 경기 원자재 한국 증시"],
        "theme_surge": ["시간외 급등 테마 주식", "장전 테마 거래대금"],
    }
    return queries or fallback.get(category, ["한국 증시"])


def _rss_urls(config: AppConfig) -> list[str]:
    value = config.env("NEWS_RSS_URLS")
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_pubdate(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return parse_datetime(parsedate_to_datetime(str(value)))
    except (TypeError, ValueError, IndexError):
        return None


def _parse_alpha_datetime(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return parse_datetime(datetime.strptime(text, "%Y%m%dT%H%M%S"))
    except ValueError:
        return parse_datetime(text)


def _strip_html(text: str) -> str:
    sanitized = re.sub(r"<[^>]+>", "", html.unescape(text or "")).strip()
    for forbidden, replacement in _PUBLIC_REPLACEMENTS.items():
        sanitized = sanitized.replace(forbidden, replacement)
    return re.sub(r"(?<![-:\d.])\b\d{6}\b(?![-:\d])", "종목코드 확인 필요", sanitized)


def _affected_sectors(title: str, summary: str) -> list[str]:
    text = f"{title} {summary}".lower()
    rules = {
        "semiconductor": ["반도체", "chip", "semiconductor", "hbm"],
        "battery": ["배터리", "battery", "2차전지", "전기차"],
        "robotics": ["로봇", "robot"],
        "defense": ["방산", "defense", "국방"],
        "bio": ["바이오", "제약", "bio"],
        "ai": ["ai", "인공지능"],
    }
    return [
        sector
        for sector, keywords in rules.items()
        if any(keyword in text for keyword in keywords)
    ]


def _alpha_topics(category: str) -> str:
    topics = {
        "political_theme": "economy_macro,financial_markets",
        "global_issue": "economy_macro,economy_monetary,financial_markets",
        "theme_surge": "financial_markets,manufacturing",
    }
    return topics.get(category, "financial_markets")


def _alpha_symbols(item: dict[str, object]) -> list[str]:
    raw_items = item.get("ticker_sentiment")
    if not isinstance(raw_items, list):
        return []
    symbols: list[str] = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        symbol = _krx_symbol_from_yahoo(str(raw.get("ticker") or ""))
        if symbol:
            symbols.append(symbol)
    return symbols


def _yfinance_tickers(config: AppConfig, category: str) -> list[str]:
    news_config = config.data_sources.get("news", {})
    raw_map = news_config.get("yfinance_tickers", {}) if isinstance(news_config, dict) else {}
    raw_tickers = raw_map.get(category, []) if isinstance(raw_map, dict) else []
    if isinstance(raw_tickers, list):
        tickers = [str(ticker).strip() for ticker in raw_tickers if str(ticker).strip()]
    else:
        tickers = []
    return tickers or ["005930.KS", "000660.KS", "^GSPC", "^IXIC"]


def _yfinance_article_fields(article: dict[str, object]) -> dict[str, object]:
    if isinstance(article.get("content"), dict):
        content = article["content"]
        provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
        url_payload = content.get("canonicalUrl") or content.get("clickThroughUrl") or {}
        if not isinstance(url_payload, dict):
            url_payload = {}
        return {
            "title": str(content.get("title") or "데이터 부족"),
            "summary": str(content.get("summary") or "데이터 부족"),
            "provider": str(provider.get("displayName") or "yfinance"),
            "url": str(url_payload.get("url") or ""),
            "published": parse_datetime(content.get("pubDate")),
        }
    published = article.get("providerPublishTime")
    if isinstance(published, (int, float)):
        published_dt = datetime.fromtimestamp(published, tz=UTC)
    else:
        published_dt = parse_datetime(published)
    return {
        "title": str(article.get("title") or "데이터 부족"),
        "summary": str(article.get("summary") or "데이터 부족"),
        "provider": str(article.get("publisher") or "yfinance"),
        "url": str(article.get("link") or ""),
        "published": parse_datetime(published_dt),
    }


def _krx_symbol_from_yahoo(ticker: str) -> str:
    symbol = ticker.upper().strip()
    for suffix in (".KS", ".KQ"):
        if symbol.endswith(suffix):
            return symbol.removesuffix(suffix)
    return symbol if re.fullmatch(r"\d{6}", symbol) else ""
