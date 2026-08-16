"""Local topic filtering for GDELT GKG archives listed in the master file."""
from __future__ import annotations

import csv
import io
import json
import random
import re
import sys
import zipfile
import time
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

import requests


def _configure_csv_field_limit() -> None:
    """GKG theme/entity fields can exceed Python CSV's small default limit."""
    limit = sys.maxsize
    while limit:
        try:
            csv.field_size_limit(limit)
            return
        except OverflowError:
            limit //= 10


_configure_csv_field_limit()


class GdeltDumpCrawler:
    """Download 15-minute GKG archives once, then filter them locally and offline."""

    MASTER_FILE_URL = "https://data.gdeltproject.org/gdeltv2/masterfilelist.txt"
    # GDELT filenames use UTC. Five evenly spaced windows reduce the chance
    # that a quick sample is dominated by one regional news cycle.
    SAMPLE_WINDOW_UTC = ("0000", "0500", "1000", "1500", "2000")
    TOPIC_EXPANSIONS = {
        "semiconductors": ("semiconductor", "chip", "chips", "tsmc", "nvidia", "micron"),
        "ai": ("artificial intelligence", "generative ai", "machine learning", "llm"),
        "entertainment": ("entertainment", "celebrity", "film", "music", "television"),
    }

    def __init__(self, cache_dir: Path, timeout: int = 60, cache_policy: str = "persistent", allow_http_fallback: bool = False) -> None:
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.cache_policy = cache_policy if cache_policy in {"persistent", "temporary"} else "persistent"
        # This is deliberately opt-in per manual run. Scheduled collection must
        # never downgrade a failed HTTPS request to HTTP.
        self.allow_http_fallback = allow_http_fallback
        self.last_failure: Exception | None = None
        self._master_urls_by_day: dict[str, list[str]] | None = None
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": "AI-Research-Lab/1.0 (local GDELT archive filter)"})

    @staticmethod
    def build_keywords(topic: str, extra_keywords: list[str] | None = None) -> list[str]:
        topic = " ".join(topic.lower().split())
        keywords = {topic} if topic else set()
        keywords.update(GdeltDumpCrawler.TOPIC_EXPANSIONS.get(topic, ()))
        keywords.update(k.lower().strip() for k in (extra_keywords or []) if k.strip())
        return sorted(keywords, key=len, reverse=True)

    def archive_path(self, day: date) -> Path:
        return self.cache_dir / f"{day:%Y%m%d}.gkg.csv.zip"

    @property
    def manifest_path(self) -> Path:
        return self.cache_dir / "manifest.json"

    def _record_cached_archive(self, day: date, path: Path) -> None:
        """Keep a reusable, date-keyed inventory shared by every topic."""
        try:
            manifest = json.loads(self.manifest_path.read_text(encoding="utf-8")) if self.manifest_path.exists() else {}
            if not isinstance(manifest, dict):
                manifest = {}
            manifest[day.isoformat()] = {"filename": path.name, "size": path.stat().st_size}
            self.manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        except (OSError, json.JSONDecodeError):
            pass

    def release_day(self, day: date) -> None:
        """Delete processed source data only in the laptop-friendly temporary mode."""
        if self.cache_policy != "temporary":
            return
        for path in self.cache_dir.glob(f"{day:%Y%m%d}*.gkg.csv.zip"):
            try:
                path.unlink(missing_ok=True)
                print(f"  [GDELT dump] temporary archive removed: {path.name}", flush=True)
            except OSError as error:
                print(f"  [Warning] cannot remove temporary archive {path.name}: {error}", flush=True)

    def download_day(self, day: date) -> Path | None:
        """Backward-compatible helper returning the first available archive for a day."""
        target = self.archive_path(day)
        if target.exists() and self._is_valid_zip(target):
            print(f"  [GDELT dump] cache hit: {target.name}", flush=True)
            if self.cache_policy == "persistent":
                self._record_cached_archive(day, target)
            return target
        paths = self._download_day_archives(day)
        return paths[0] if paths else None

    def _master_urls(self) -> dict[str, list[str]] | None:
        if self._master_urls_by_day is not None:
            return self._master_urls_by_day
        print("  [GDELT dump] loading master file list", flush=True)
        try:
            response = self._download(self.MASTER_FILE_URL)
            response.raise_for_status()
            grouped: dict[str, list[str]] = {}
            for line in response.text.splitlines():
                url = next((part for part in line.split() if part.endswith(".gkg.csv.zip")), "")
                name = Path(urlparse(url).path).name
                if len(name) < 8 or not name[:8].isdigit():
                    continue
                grouped.setdefault(f"{name[:4]}-{name[4:6]}-{name[6:8]}", []).append(url)
            self._master_urls_by_day = grouped
            self.last_failure = None
            return grouped
        except requests.RequestException as error:
            self.last_failure = error
            print(f"  [Warning] GDELT master file list unavailable: {error}", flush=True)
            return None

    def _download_day_archives(self, day: date) -> list[Path]:
        grouped = self._master_urls()
        if grouped is None:
            return []
        urls = grouped.get(day.isoformat(), [])
        print(f"  [GDELT dump] {len(urls)} GKG blocks listed for {day}", flush=True)
        paths: list[Path] = []
        for url in urls:
            target = self.cache_dir / Path(urlparse(url).path).name
            path = self._download_archive(day, url, target)
            if path is None:
                return []
            paths.append(path)
        self.last_failure = None
        return paths

    def _day_archive_urls(self, day: date) -> list[str] | None:
        grouped = self._master_urls()
        if grouped is None:
            return None
        urls = grouped.get(day.isoformat(), [])
        print(f"  [GDELT dump] {len(urls)} GKG blocks listed for {day}", flush=True)
        return urls

    @classmethod
    def _balanced_sample_entries(cls, entries: list[tuple[str | None, Path]]) -> list[tuple[str | None, Path]]:
        """Choose one 15-minute file near each evenly spaced UTC window."""
        selected: list[tuple[str | None, Path]] = []
        for target in cls.SAMPLE_WINDOW_UTC:
            def distance(entry: tuple[str | None, Path]) -> int:
                name = entry[1].name
                clock = name[8:12] if len(name) >= 12 else "0000"
                return abs(int(clock[:2]) * 60 + int(clock[2:]) - (int(target[:2]) * 60 + int(target[2:])))
            candidate = min(entries, key=distance, default=None)
            if candidate is not None and candidate not in selected:
                selected.append(candidate)
        if selected:
            labels = ", ".join(path.name[8:12] for _, path in selected)
            print(f"  [GDELT dump] balanced sample windows (UTC): {labels}", flush=True)
        return selected

    @classmethod
    def _fallback_sample_entries(cls, entries: list[tuple[str | None, Path]]) -> list[tuple[str | None, Path]]:
        """Order extra blocks by proximity to one of the balanced UTC windows."""
        def distance(entry: tuple[str | None, Path]) -> int:
            name = entry[1].name
            clock = name[8:12] if len(name) >= 12 else "0000"
            minute = int(clock[:2]) * 60 + int(clock[2:])
            return min(abs(minute - (int(target[:2]) * 60 + int(target[2:]))) for target in cls.SAMPLE_WINDOW_UTC)
        return sorted(entries, key=distance)

    def _download_archive(self, day: date, url: str, target: Path) -> Path | None:
        if target.exists() and self._is_valid_zip(target):
            print(f"  [GDELT dump] cache hit: {target.name}", flush=True)
            if self.cache_policy == "persistent":
                self._record_cached_archive(day, target)
            return target
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(target.suffix + ".part")
        print(f"  [GDELT dump] downloading: {target.name}", flush=True)
        try:
            response = self._download(url)
            response.raise_for_status()
            with temporary.open("wb") as handle:
                for chunk in response.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        handle.write(chunk)
            if not self._is_valid_zip(temporary):
                raise zipfile.BadZipFile("downloaded archive failed ZIP validation")
            temporary.replace(target)
            if self.cache_policy == "persistent":
                self._record_cached_archive(day, target)
        except (OSError, requests.RequestException, zipfile.BadZipFile) as error:
            self.last_failure = error
            print(f"  [Warning] GDELT dump unavailable for {day}: {error}", flush=True)
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            return None
        self.last_failure = None
        return target

    def _download(self, url: str) -> requests.Response:
        secure_url = url.replace("http://data.gdeltproject.org/", "https://data.gdeltproject.org/", 1)
        try:
            return self.session.get(secure_url, stream=True, timeout=self.timeout)
        except requests.exceptions.SSLError:
            if not self.allow_http_fallback:
                raise
            http_url = secure_url.replace("https://", "http://", 1)
            print("  [Security warning] HTTPS certificate verification failed; using user-approved HTTP for this run only.", flush=True)
            return self.session.get(http_url, stream=True, timeout=self.timeout)

    @property
    def last_failure_needs_http_consent(self) -> bool:
        return isinstance(self.last_failure, requests.exceptions.SSLError)

    @staticmethod
    def _is_valid_zip(path: Path) -> bool:
        try:
            with zipfile.ZipFile(path) as archive:
                return archive.testzip() is None
        except (OSError, zipfile.BadZipFile):
            return False

    def filter_day(self, day: date, topic: str, limit: int, extra_keywords: list[str] | None = None,
                   scan_mode: str = "sample") -> list[dict]:
        # Keep support for a manually supplied legacy daily archive used by
        # existing local caches/tests, but live collection uses master-list blocks.
        # Each day is independently retriable. Do not let an earlier TLS error
        # turn a later cache hit into a false "pending" result.
        self.last_failure = None
        full_scan = scan_mode == "full"
        started_at = time.monotonic()
        legacy = self.archive_path(day)
        if legacy.exists() and self._is_valid_zip(legacy):
            archive_entries: list[tuple[str | None, Path]] = [(None, legacy)]
        else:
            urls = self._day_archive_urls(day)
            if urls is None:
                return []
            archive_entries = [(url, self.cache_dir / Path(urlparse(url).path).name) for url in urls]
        if not archive_entries:
            return []
        primary_sample_count = len(archive_entries)
        if not full_scan and len(archive_entries) > 1:
            primary_entries = self._balanced_sample_entries(archive_entries)
            fallback_entries = self._fallback_sample_entries(
                [entry for entry in archive_entries if entry not in primary_entries]
            )
            archive_entries = primary_entries + fallback_entries
            primary_sample_count = len(primary_entries)
        keywords = self.build_keywords(topic, extra_keywords)
        results: list[dict] = []
        seen_urls: set[str] = set()
        matched_count = 0
        sampler = random.Random(f"{day.isoformat()}:{topic.lower()}")
        sample_quotas = []
        if not full_scan:
            base, remainder = divmod(limit, primary_sample_count)
            sample_quotas = [base + (1 if index < remainder else 0) for index in range(primary_sample_count)]
        for archive_index, (archive_url, candidate_path) in enumerate(archive_entries):
            if not full_scan and len(results) >= limit:
                break
            if not full_scan and archive_index == primary_sample_count and len(results) < limit:
                print(f"  [GDELT dump] balanced windows yielded {len(results)}/{limit}; checking nearby blocks for the shortfall", flush=True)
            slot_limit = sample_quotas[archive_index] if archive_index < primary_sample_count else limit - len(results)
            if not full_scan and slot_limit <= 0:
                continue
            archive_path = candidate_path if archive_url is None else self._download_archive(day, archive_url, candidate_path)
            if archive_path is None:
                return []
            slot_count = 0
            try:
                with zipfile.ZipFile(archive_path) as archive:
                    name = archive.namelist()[0]
                    with archive.open(name) as binary, io.TextIOWrapper(binary, encoding="utf-8", errors="replace", newline="") as text:
                        for row in csv.reader(text, delimiter="\t"):
                            if len(row) < 5:
                                continue
                            haystack = " ".join(row).lower()
                            matched = next((keyword for keyword in keywords if keyword in haystack), None)
                            if not matched:
                                continue
                            url = row[4].strip()
                            if not url or url in seen_urls:
                                continue
                            seen_urls.add(url)
                            source = row[3].strip() or urlparse(url).netloc or "GDELT GKG"
                            record_date = row[1].strip() if len(row) > 1 else f"{day:%Y%m%d}"
                            themes = row[8].strip() if len(row) > 8 else ""
                            article = {
                                "source": source,
                                "title": f"{matched}: {source}",
                                "url": url,
                                "summary": themes[:500],
                                "date": record_date,
                                "kind": "news",
                                "time_status": "known" if record_date else "unknown",
                                "platform": "gdelt_dump",
                                "community": "",
                            }
                            matched_count += 1
                            if len(results) < limit:
                                results.append(article)
                                slot_count += 1
                            elif full_scan:
                                replacement = sampler.randrange(matched_count)
                                if replacement < limit:
                                    results[replacement] = article
                            if not full_scan and slot_count >= slot_limit:
                                break
            except (OSError, zipfile.BadZipFile) as error:
                print(f"  [Warning] cannot read {archive_path.name}: {error}", flush=True)
        if full_scan:
            elapsed = time.monotonic() - started_at
            print(f"  [GDELT dump] full scan complete: {matched_count} matching articles across {len(archive_entries)} blocks in {elapsed:.1f}s", flush=True)
        return results
