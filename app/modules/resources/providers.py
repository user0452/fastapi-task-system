import html
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

import requests

from app.core.config import get_settings

TRACKING_KEYS = {
    "spm_id_from",
    "vd_source",
    "feature",
    "si",
    "share_source",
    "share_medium",
}
ALLOWED_VIDEO_HOSTS = {
    "bilibili.com",
    "m.bilibili.com",
    "www.bilibili.com",
    "youtube.com",
    "m.youtube.com",
    "www.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
    "youtu.be",
    "www.youtu.be",
}
CANONICAL_VIDEO_HOSTS = {
    "m.bilibili.com": "bilibili.com",
    "www.bilibili.com": "bilibili.com",
    "m.youtube.com": "youtube.com",
    "www.youtube.com": "youtube.com",
    "www.youtube-nocookie.com": "youtube-nocookie.com",
    "www.youtu.be": "youtu.be",
}
ALLOWED_IMAGE_HOSTS = {
    "archive.biliimg.com",
    "img.youtube.com",
    "i.ytimg.com",
    "s1.hdslb.com",
    *(f"i{index}.hdslb.com" for index in range(10)),
}


@dataclass
class ResourceCandidate:
    provider: str
    provider_resource_id: str | None
    resource_type: str
    canonical_url: str
    title: str
    author: str | None = None
    summary: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: int | None = None
    published_at: datetime | None = None
    language: str = "zh-CN"
    relevance_score: float = 0.0
    quality_score: float = 0.0
    metadata: dict | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class ResourceProvider(Protocol):
    name: str

    def search(self, course_name: str, topic: str, max_results: int) -> list[ResourceCandidate]: ...


class DeterministicVideoProvider:
    """Offline provider used only when the application explicitly enables mock mode."""

    name = "mock-video"
    video_ids = ["UTKS3UKUCUs", "pt2dwKgFD4k", "tax-Y0Rd7PA", "Ui4Mo5b31Vw"]

    def search(self, course_name: str, topic: str, max_results: int) -> list[ResourceCandidate]:
        labels = ["概念入门", "案例拆解", "常见误区", "练习复盘"]
        return [
            ResourceCandidate(
                provider="youtube",
                provider_resource_id=video_id,
                resource_type="video",
                canonical_url=f"https://youtube.com/watch?v={video_id}",
                title=f"{course_name} · {topic} · {labels[index]}",
                author="A3 离线验收资源",
                summary=f"用于验证 {topic} 的外部视频推荐、封面和学习状态闭环。",
                thumbnail_url=f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                duration_seconds=480 + index * 180,
                relevance_score=0.96 - index * 0.03,
                quality_score=0.8,
                metadata={"mock": True},
            )
            for index, video_id in enumerate(self.video_ids[:max_results])
        ]


def canonicalize_url(value: str) -> str | None:
    try:
        parsed = urlparse((value or "").strip())
    except ValueError:
        return None
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    try:
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return None
    if (
        host not in ALLOWED_VIDEO_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 80, 443}
    ):
        return None
    host = CANONICAL_VIDEO_HOSTS.get(host, host)
    query = []
    for key, item in parse_qsl(parsed.query, keep_blank_values=False):
        if key.lower().startswith("utm_") or key.lower() in TRACKING_KEYS:
            continue
        if host == "bilibili.com":
            continue
        if host in {"youtube.com", "youtube-nocookie.com"} and key != "v":
            continue
        query.append((key, item))
    return urlunparse(("https", host, parsed.path.rstrip("/"), "", urlencode(query), ""))


def normalize_image_url(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    if normalized.startswith("//"):
        normalized = "https:" + normalized
    if normalized.startswith("http://"):
        normalized = "https://" + normalized[7:]
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    try:
        host = (parsed.hostname or "").lower().rstrip(".")
        port = parsed.port
    except ValueError:
        return None
    if (
        host not in ALLOWED_IMAGE_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or port not in {None, 80, 443}
    ):
        return None
    lowered = parsed.path.lower()
    if "favicon" in lowered or "transparent.png" in lowered:
        return None
    return normalized


def _plain_text(value: str | None) -> str:
    without_tags = re.sub(r"<[^>]+>", "", value or "")
    return html.unescape(without_tags).strip()


def _response_json(response: requests.Response, provider: str) -> dict:
    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{provider} returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{provider} returned a non-object JSON payload")
    return payload


def _duration_seconds(value) -> int | None:
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("PT"):
        match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", text)
        if not match:
            return None
        hours, minutes, seconds = (int(item or 0) for item in match.groups())
        return hours * 3600 + minutes * 60 + seconds
    parts = text.split(":")
    if all(part.isdigit() for part in parts):
        total = 0
        for part in parts:
            total = total * 60 + int(part)
        return total
    return None


def _youtube_id(url: str) -> str | None:
    match = re.search(
        r"(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:[^#]*&)?v=|shorts/|embed/|live/)|youtu\.be/)"
        r"([a-zA-Z0-9_-]{11})",
        url,
    )
    return match.group(1) if match else None


def _bilibili_id(url: str) -> str | None:
    match = re.search(r"bilibili\.com/video/(BV[a-zA-Z0-9]+)", url)
    return match.group(1) if match else None


class BilibiliProvider:
    name = "bilibili"
    search_url = "https://api.bilibili.com/x/web-interface/search/type"

    def search(self, course_name: str, topic: str, max_results: int) -> list[ResourceCandidate]:
        timeout = get_settings().external_resource_timeout_seconds
        response = requests.get(
            self.search_url,
            params={
                "search_type": "video",
                "keyword": f"{course_name} {topic} 教程",
                "page": 1,
                "page_size": min(20, max_results * 3),
            },
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124 Safari/537.36",
                "Referer": "https://search.bilibili.com/",
            },
            timeout=timeout,
        )
        response.raise_for_status()
        body = _response_json(response, self.name)
        if body.get("code") != 0:
            raise RuntimeError(body.get("message") or "Bilibili 搜索暂时不可用")
        rows = body.get("data", {}).get("result") or []
        candidates = []
        for index, row in enumerate(rows):
            bvid = row.get("bvid")
            if not bvid:
                continue
            url = canonicalize_url(f"https://www.bilibili.com/video/{bvid}")
            if not url:
                continue
            published = None
            if row.get("pubdate"):
                try:
                    published = datetime.fromtimestamp(int(row["pubdate"]), tz=timezone.utc)
                except (TypeError, ValueError, OSError):
                    published = None
            candidates.append(
                ResourceCandidate(
                    provider=self.name,
                    provider_resource_id=bvid,
                    resource_type="video",
                    canonical_url=url,
                    title=_plain_text(row.get("title")) or "Bilibili 视频",
                    author=_plain_text(row.get("author")) or None,
                    summary=_plain_text(row.get("description"))[:500] or None,
                    thumbnail_url=normalize_image_url(row.get("pic")),
                    duration_seconds=_duration_seconds(row.get("duration")),
                    published_at=published,
                    relevance_score=max(0.25, 0.75 - index * 0.04),
                    quality_score=min(1.0, float(row.get("play") or 0) / 100000),
                    metadata={"favorites": row.get("favorites"), "play": row.get("play")},
                )
            )
            if len(candidates) >= max_results:
                break
        return candidates


class YouTubeProvider:
    name = "youtube"
    search_url = "https://www.googleapis.com/youtube/v3/search"
    videos_url = "https://www.googleapis.com/youtube/v3/videos"

    def search(self, course_name: str, topic: str, max_results: int) -> list[ResourceCandidate]:
        settings = get_settings()
        if not settings.youtube_api_key:
            return []
        params = {
            "key": settings.youtube_api_key,
            "part": "snippet",
            "q": f"{course_name} {topic} tutorial",
            "type": "video",
            "maxResults": max_results,
            "relevanceLanguage": "zh-Hans",
            "safeSearch": "moderate",
        }
        response = requests.get(self.search_url, params=params, timeout=settings.external_resource_timeout_seconds)
        response.raise_for_status()
        items = _response_json(response, self.name).get("items") or []
        video_ids = [item.get("id", {}).get("videoId") for item in items]
        video_ids = [item for item in video_ids if item]
        details = {}
        if video_ids:
            detail_response = requests.get(
                self.videos_url,
                params={
                    "key": settings.youtube_api_key,
                    "part": "contentDetails,statistics",
                    "id": ",".join(video_ids),
                },
                timeout=settings.external_resource_timeout_seconds,
            )
            detail_response.raise_for_status()
            details = {
                item["id"]: item
                for item in _response_json(detail_response, self.name).get("items") or []
            }
        candidates = []
        for item in items:
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            snippet = item.get("snippet") or {}
            detail = details.get(video_id, {})
            statistics = detail.get("statistics") or {}
            published = None
            if snippet.get("publishedAt"):
                try:
                    published = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))
                except ValueError:
                    published = None
            thumbnail = (snippet.get("thumbnails") or {}).get("high", {}).get("url")
            candidates.append(
                ResourceCandidate(
                    provider=self.name,
                    provider_resource_id=video_id,
                    resource_type="video",
                    canonical_url=f"https://youtube.com/watch?v={video_id}",
                    title=_plain_text(snippet.get("title")) or "YouTube 视频",
                    author=_plain_text(snippet.get("channelTitle")) or None,
                    summary=_plain_text(snippet.get("description"))[:500] or None,
                    thumbnail_url=normalize_image_url(thumbnail) or f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
                    duration_seconds=_duration_seconds((detail.get("contentDetails") or {}).get("duration")),
                    published_at=published,
                    relevance_score=0.8,
                    quality_score=min(1.0, float(statistics.get("viewCount") or 0) / 1000000),
                    metadata={"view_count": statistics.get("viewCount")},
                )
            )
        return candidates


class TavilyVideoProvider:
    name = "tavily"
    search_url = "https://api.tavily.com/search"

    def search(self, course_name: str, topic: str, max_results: int) -> list[ResourceCandidate]:
        settings = get_settings()
        if not settings.tavily_api_key:
            return []
        response = requests.post(
            self.search_url,
            headers={
                "Authorization": f"Bearer {settings.tavily_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "query": f"{course_name} {topic} 视频教程",
                "search_depth": "basic",
                "max_results": min(20, max_results * 4),
                "topic": "general",
                "include_answer": False,
                "include_raw_content": False,
                "include_images": True,
                "include_domains": ["bilibili.com", "youtube.com", "youtu.be"],
            },
            timeout=settings.external_resource_timeout_seconds,
        )
        response.raise_for_status()
        body = _response_json(response, self.name)
        candidates = []
        for row in body.get("results") or []:
            raw_url = row.get("url") or ""
            url = canonicalize_url(raw_url)
            if not url:
                continue
            youtube_id = _youtube_id(url)
            bilibili_id = _bilibili_id(url)
            if not youtube_id and not bilibili_id:
                continue
            provider = "youtube" if youtube_id else "bilibili"
            resource_id = youtube_id or bilibili_id
            image = row.get("thumbnail") or row.get("image_url") or row.get("image")
            if not image and youtube_id:
                image = f"https://img.youtube.com/vi/{youtube_id}/hqdefault.jpg"
            candidates.append(
                ResourceCandidate(
                    provider=provider,
                    provider_resource_id=resource_id,
                    resource_type="video",
                    canonical_url=url,
                    title=_plain_text(row.get("title")) or f"{provider} 视频",
                    summary=_plain_text(row.get("content"))[:500] or None,
                    thumbnail_url=normalize_image_url(image),
                    relevance_score=max(0.0, min(1.0, float(row.get("score") or 0))),
                    quality_score=0.5,
                    metadata={"discovered_by": self.name},
                )
            )
            if len(candidates) >= max_results:
                break
        return candidates
