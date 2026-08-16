"""GDELT DOC 2.0 API를 통한 날짜 범위 뉴스 수집기."""
from __future__ import annotations

from datetime import datetime, timezone
from collections import defaultdict
import random
import time

import requests


class GdeltCrawler:
    """Public GDELT DOC API client.  No API key is required."""

    SEARCH_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
    MAX_RETRIES = 2

    SOURCE_LANGUAGE_VALUES = {"global", "korean", "english"}
    REGION_PROFILE_VALUES = {"global_even", "country_focus", "korea_focus"}

    def __init__(
        self,
        source_language: str = "global",
        region_profile: str = "global_even",
        target_country: str = "",
        timeout: int = 15,
    ) -> None:
        self.source_language = (
            source_language.lower().strip()
            if source_language.lower().strip() in self.SOURCE_LANGUAGE_VALUES
            else "global"
        )
        self.region_profile = "country_focus" if region_profile == "korea_focus" else (
            region_profile if region_profile in self.REGION_PROFILE_VALUES else "global_even"
        )
        self.target_country = target_country
        self.timeout = timeout
        self.last_response_seconds: float | None = None
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AI-Research-Lab/1.0 (research digest)"})

    @property
    def is_configured(self) -> bool:
        return True

    @staticmethod
    def _api_datetime(value: datetime) -> str:
        return value.astimezone(timezone.utc).strftime("%Y%m%d%H%M%S")

    def fetch(
        self,
        topic: str,
        limit: int,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> list[dict]:
        if limit <= 0:
            return []
        params = {
            "query": topic,
            "mode": "artlist",
            "format": "json",
            "maxrecords": min(max(limit, 50), 250),
        }
        if self.source_language != "global":
            params["query"] = f"{topic} sourcelang:{self.source_language}"
        if window_start is not None:
            params["startdatetime"] = self._api_datetime(window_start)
        if window_end is not None:
            params["enddatetime"] = self._api_datetime(window_end)
        if window_start is None and window_end is None:
            params["timespan"] = "1d"
        self.last_response_seconds = None
        payload = None
        rate_limit_delay: float | None = None
        for attempt in range(self.MAX_RETRIES + 1):
            try:
                request_started = time.monotonic()
                range_label = (
                    f"{params.get('startdatetime', 'latest')} to "
                    f"{params.get('enddatetime', 'latest')}"
                )
                print(
                    f"  [GDELT] request {attempt + 1}/{self.MAX_RETRIES + 1} started; range={range_label}; "
                    f"timeout={self.timeout}s",
                    flush=True,
                )
                response = self.session.get(self.SEARCH_URL, params=params, timeout=self.timeout)
                if getattr(response, "status_code", None) == 429:
                    if attempt >= self.MAX_RETRIES:
                        response.raise_for_status()
                    retry_after = getattr(response, "headers", {}).get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        delay = float(retry_after)
                    elif rate_limit_delay is None:
                        # Observed DOC API responses need a materially longer
                        # cool-down than the former 30-second retry interval.
                        delay = random.uniform(75.0, 90.0)
                    else:
                        delay = min(rate_limit_delay * 1.5 + random.uniform(5.0, 15.0), 180.0)
                    rate_limit_delay = delay
                    print(
                        f"  [Warning] GDELT rate limited after {time.monotonic() - request_started:.1f}s; "
                        f"retrying in {delay:.2f}s (attempt {attempt + 1}/{self.MAX_RETRIES + 1})",
                        flush=True,
                    )
                    time.sleep(delay)
                    continue
                response.raise_for_status()
                payload = response.json()
                self.last_response_seconds = time.monotonic() - request_started
                print(
                    f"  [GDELT] response received in {self.last_response_seconds:.1f}s; "
                    f"candidates={len(payload.get('articles', []))}",
                    flush=True,
                )
                break
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as error:
                if attempt >= self.MAX_RETRIES:
                    print(f"  [Warning] '{topic}' GDELT network failure: {error}", flush=True)
                    return []
                print(
                    f"  [Warning] '{topic}' GDELT network failure; retrying in 10.0s "
                    f"(attempt {attempt + 1}/{self.MAX_RETRIES + 1}): {error}",
                    flush=True,
                )
                time.sleep(10.0)
                continue
            except (requests.RequestException, ValueError) as error:
                print(
                    f"  [Warning] '{topic}' GDELT search failed after "
                    f"{time.monotonic() - request_started:.1f}s: {error}",
                    flush=True,
                )
                return []
        if payload is None:
            return []

        candidates: list[dict] = []
        for article in payload.get("articles", []):
            title = (article.get("title") or "").strip()
            url = (article.get("url") or "").strip()
            if not title or not url:
                continue
            source = (article.get("domain") or "GDELT").strip()
            seen_date = (article.get("seendate") or "").strip()
            candidates.append({
                "source": source,
                "title": title,
                "url": url,
                "summary": "",
                "date": seen_date,
                "kind": "news",
                "time_status": "known" if seen_date else "unknown",
                "platform": "gdelt",
                "community": "",
                "source_country": (article.get("sourcecountry") or "").strip(),
                "_diversity_key": (
                    article.get("sourcecountry")
                    or article.get("language")
                    or source
                ).lower(),
            })
        if self.region_profile == "country_focus":
            results = self._select_country_focus(candidates, limit)
        else:
            results = self._select_round_robin(candidates, limit)
        for article in results:
            article.pop("_diversity_key", None)
        return results

    @staticmethod
    def _select_round_robin(candidates: list[dict], limit: int) -> list[dict]:
        """Avoid one country/language dominating a global relevance ranking."""
        buckets: dict[str, list[dict]] = {}
        for article in candidates:
            buckets.setdefault(article["_diversity_key"], []).append(article)
        results: list[dict] = []
        while buckets and len(results) < limit:
            for key in list(buckets):
                results.append(buckets[key].pop(0))
                if not buckets[key]:
                    del buckets[key]
                if len(results) >= limit:
                    break
        return results

    @staticmethod
    def _country_key(article: dict) -> str:
        country = str(article.get("source_country", "")).lower().replace(" ", "")
        if country in {"southkorea", "korea,south", "republicofkorea", "korea"}:
            return "korea"
        if country in {"unitedstates", "unitedstatesofamerica", "usa", "us"}:
            return "us"
        if country in {"china", "peoplesrepublicofchina"}:
            return "china"
        if country in {"japan"}:
            return "japan"
        return "other"

    def _select_country_focus(self, candidates: list[dict], limit: int) -> list[dict]:
        """Give the output-language country half the slots, then diversify globally."""
        target = {"KR": "korea", "US": "us", "CN": "china", "JP": "japan"}.get(
            self.target_country.upper(), "other"
        )
        # Recommended residual mix: leading global market 20%, second market 15%,
        # third market 5%, and all other countries 10%.
        priority = [key for key in ("us", "china", "korea", "japan") if key != target]
        weights = [(target, 0.50), (priority[0], 0.20), (priority[1], 0.15), (priority[2], 0.05), ("other", 0.10)]
        grouped: dict[str, list[dict]] = defaultdict(list)
        for article in candidates:
            grouped[self._country_key(article)].append(article)

        selected: list[dict] = []
        selected_urls: set[str] = set()
        for region, weight in weights:
            target = round(limit * weight)
            for article in grouped[region][:target]:
                selected.append(article)
                selected_urls.add(article["url"])

        if len(selected) < limit:
            remaining = [article for article in candidates if article["url"] not in selected_urls]
            selected.extend(self._select_round_robin(remaining, limit - len(selected)))
        return selected[:limit]

    def validate_connection(self) -> tuple[bool, str]:
        """Verify public API access with a single small request."""
        try:
            response = self.session.get(
                self.SEARCH_URL,
                params={"query": "AI", "mode": "artlist", "format": "json", "maxrecords": 1, "timespan": "1d"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as error:
            return False, f"connection failed ({error})"
        return True, "connected (no API key required)"
