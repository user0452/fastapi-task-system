from app.integrations.llm.agent_responder import generate_agent_reply
from services import external_resource_service


class _FailingLlm:
    def invoke(self, _messages):
        raise TimeoutError("provider unavailable")


def test_tavily_failure_returns_degraded_empty_result(monkeypatch):
    def fail_search(*_args, **_kwargs):
        raise TimeoutError("tavily unavailable")

    monkeypatch.setattr(external_resource_service, "_call_tavily_search", fail_search)

    result = external_resource_service.search_external_learning_resources(
        course_name="软件测试",
        topic="等价类划分",
        max_results=5,
    )

    assert result["resources"] == []
    assert result["total"] == 0
    assert result["degraded"] is True
    assert "课程资料学习" in result["warning"]


def test_cover_failure_falls_back_to_search_result_image(monkeypatch):
    monkeypatch.setattr(external_resource_service, "_get_video_thumbnail", lambda _url: None)

    result = external_resource_service._normalize_tavily_result(
        {
            "title": "等价类划分视频教程",
            "url": "https://www.bilibili.com/video/BV1xx411c7mD",
            "content": "通过案例讲解等价类划分。",
            "image_url": "//cdn.example.com/covers/equivalence.jpg",
            "score": 0.9,
        },
        topic="等价类划分",
        learner_level="beginner",
    )

    assert result["resource_type"] == "video"
    assert result["thumbnail"] == "https://cdn.example.com/covers/equivalence.jpg"


def test_common_youtube_urls_generate_a_thumbnail():
    video_id = "dQw4w9WgXcQ"
    urls = [
        f"https://www.youtube.com/watch?v={video_id}",
        f"https://youtu.be/{video_id}",
        f"https://www.youtube.com/shorts/{video_id}",
        f"https://www.youtube-nocookie.com/embed/{video_id}",
    ]

    for url in urls:
        assert external_resource_service._get_video_thumbnail(url) == (
            f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg"
        )


def test_malformed_external_result_does_not_hide_valid_resources(monkeypatch):
    responses = [
        [
            {
                "title": "有效视频",
                "url": "https://youtu.be/dQw4w9WgXcQ",
                "content": "有效的课程讲解",
                "score": 0.8,
            },
            {"title": "坏数据", "url": 123, "image": {"unexpected": True}},
        ],
        [],
        [],
    ]
    monkeypatch.setattr(
        external_resource_service,
        "_call_tavily_search",
        lambda *_args, **_kwargs: responses.pop(0),
    )

    result = external_resource_service.search_external_learning_resources(
        "软件测试",
        "边界值分析",
    )

    assert result["total"] == 1
    assert result["resources"][0]["title"] == "有效视频"
    assert result["degraded"] is True


def test_llm_failure_still_answers_from_course_citation(monkeypatch):
    monkeypatch.setattr(
        "app.integrations.llm.agent_responder.get_settings",
        lambda: type("Settings", (), {"mock_llm": False})(),
    )
    citations = [
        {
            "chunk_id": 7,
            "material_title": "课程讲义",
            "snippet": "有效等价类表示符合输入约束的数据集合。",
        }
    ]

    reply = generate_agent_reply(
        "什么是有效等价类？",
        {"id": 1, "name": "软件测试"},
        None,
        [],
        [],
        citations,
        "2026-07-12 10:30 +08:00",
        llm_provider=lambda: _FailingLlm(),
    )

    assert "软件测试" in reply
    assert citations[0]["snippet"] in reply
    assert "练习：" in reply
    assert "三天计划：" in reply
