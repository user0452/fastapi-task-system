import os
from urllib.parse import urlparse

import requests

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def _get_tavily_api_key() -> str:
    api_key = os.getenv("TAVILY_API_KEY")

    if not api_key:
        raise ValueError("未配置 TAVILY_API_KEY，请先在 .env 中配置 Tavily API Key")

    return api_key


def _get_domain(url: str) -> str:
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def _classify_resource_type(title: str, url: str, content: str) -> str:
    """
    根据 URL、标题和摘要简单判断资源类型。
    第一版以 URL 和标题为主，避免被网页导航里的无关词误导。
    """
    title_lower = (title or "").lower()
    url_lower = (url or "").lower()
    content_lower = (content or "").lower()
    domain = _get_domain(url)

    if url_lower.endswith(".pdf") or "[pdf]" in title_lower or "pdf" in title_lower:
        return "document"

    if any(site in domain for site in [
        "bilibili.com",
        "youtube.com",
        "youtu.be",
        "youku.com",
        "ixigua.com"
    ]):
        return "video"

    if any(word in title_lower for word in [
        "视频",
        "视频教程",
        "公开课",
        "网课",
        "lecture",
        "video"
    ]):
        return "video"

    if any(word in title_lower for word in [
        "练习",
        "习题",
        "题库",
        "案例",
        "实战",
        "exercise",
        "practice",
        "quiz"
    ]):
        return "practice"

    if any(word in title_lower for word in [
        "文档",
        "官方文档",
        "documentation",
        "docs",
        "manual"
    ]):
        return "document"

    if any(word in content_lower[:300] for word in [
        "练习题",
        "测试用例设计",
        "案例分析"
    ]):
        return "practice"

    return "article"


def _estimate_time(resource_type: str) -> str:
    if resource_type == "video":
        return "15-40分钟"
    if resource_type == "practice":
        return "20-45分钟"
    if resource_type == "document":
        return "15-30分钟"
    return "10-20分钟"

def _get_resource_type_priority(resource_type: str) -> int:
    priority_map = {
        "video": 4,
        "practice": 3,
        "document": 2,
        "article": 1
    }

    return priority_map.get(resource_type, 0)

def _build_reason(topic: str, learner_level: str, resource_type: str) -> str:
    type_name_map = {
        "video": "视频讲解",
        "article": "图文资料",
        "document": "文档资料",
        "practice": "练习材料"
    }

    type_name = type_name_map.get(resource_type, "学习资料")

    if learner_level == "beginner":
        return f"该{type_name}与“{topic}”相关，适合作为入门阶段的补充学习资源。"

    if learner_level == "advanced":
        return f"该{type_name}可用于进一步理解“{topic}”，适合作为进阶拓展材料。"

    return f"该{type_name}与“{topic}”相关，可作为当前学习阶段的补充资料。"


def _call_tavily_search(query: str, max_results: int = 5) -> list[dict]:
    api_key = _get_tavily_api_key()

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "query": query,
        "search_depth": "basic",
        "max_results": max_results,
        "topic": "general",
        "include_answer": False,
        "include_raw_content": False,
        "include_favicon": True
    }

    response = requests.post(
        TAVILY_SEARCH_URL,
        headers=headers,
        json=payload,
        timeout=20
    )

    if response.status_code == 401:
        raise ValueError("Tavily API Key 无效或未授权")

    if response.status_code == 429:
        raise ValueError("Tavily 调用频率过高或额度不足")

    if response.status_code >= 400:
        raise ValueError(f"Tavily 搜索失败：{response.status_code} {response.text}")

    data = response.json()

    return data.get("results", [])


def _normalize_tavily_result(
        raw_result: dict,
        topic: str,
        learner_level: str
) -> dict:
    title = raw_result.get("title") or "未命名资源"
    url = raw_result.get("url") or ""
    content = raw_result.get("content") or ""
    score = raw_result.get("score", 0)
    favicon = raw_result.get("favicon")

    resource_type = _classify_resource_type(
        title=title,
        url=url,
        content=content
    )

    snippet = content.strip()

    if len(snippet) > 300:
        snippet = snippet[:300] + "..."

    return {
        "title": title,
        "url": url,
        "source": _get_domain(url),
        "resource_type": resource_type,
        "difficulty": learner_level,
        "reason": _build_reason(
            topic=topic,
            learner_level=learner_level,
            resource_type=resource_type
        ),
        "estimated_time": _estimate_time(resource_type),
        "snippet": snippet,
        "score": score,
        "favicon": favicon
    }


def search_external_learning_resources(
        course_name: str,
        topic: str,
        learner_level: str = "beginner",
        max_results: int = 8
) -> dict:
    """
    联网搜索外部学习资源。
    第一版使用 Tavily，返回结构化学习资源卡片。
    """
    query_list = [
        f"{course_name} {topic} 教程 学习资料",
        f"{course_name} {topic} 练习 案例 教程",
        f"{course_name} {topic} B站 视频 教程"
    ]

    raw_results = []
    seen_urls = set()

    per_query_limit = max(3, min(5, max_results))

    for query in query_list:
        results = _call_tavily_search(
            query=query,
            max_results=per_query_limit
        )

        for item in results:
            url = item.get("url")

            if not url:
                continue

            if url in seen_urls:
                continue

            seen_urls.add(url)
            raw_results.append(item)

    normalized_resources = [
        _normalize_tavily_result(
            raw_result=item,
            topic=topic,
            learner_level=learner_level
        )
        for item in raw_results
    ]

    normalized_resources.sort(
        key=lambda item: (
            _get_resource_type_priority(item.get("resource_type")),
            item.get("score", 0)
        ),
        reverse=True
    )

    return {
        "course_name": course_name,
        "topic": topic,
        "learner_level": learner_level,
        "queries": query_list,
        "total": min(len(normalized_resources), max_results),
        "resources": normalized_resources[:max_results]
    }