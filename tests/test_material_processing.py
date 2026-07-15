import asyncio
from io import BytesIO

import numpy as np
import pytest
from starlette.datastructures import Headers, UploadFile

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations import file_storage
from app.integrations.llm import knowledge_extractor
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import create_user_course, get_user_course
from app.modules.materials import service as materials_service
from app.modules.materials.schemas import TextMaterialCreate
from app.modules.materials.service import (
    create_text_material,
    delete_user_material,
    get_user_material,
    list_course_knowledge_points,
    process_material,
)


def _fake_embeddings(texts: list[str]) -> np.ndarray:
    rows = []
    for index, _ in enumerate(texts):
        vector = np.array([1.0, float(index + 1), 0.5], dtype="float32")
        vector /= np.linalg.norm(vector)
        rows.append(vector)
    return np.vstack(rows)


def _fake_knowledge_points(_course_name: str, title: str, chunks: list[dict]) -> list[dict]:
    indices = [chunk["chunk_index"] for chunk in chunks]
    return [
        {
            "name": f"{title}知识点{index + 1}",
            "description": "用于验证自动知识点提取",
            "chunk_indices": [indices[index % len(indices)]],
        }
        for index in range(3)
    ]


def test_text_material_is_automatically_indexed_with_sources(two_users):
    user, _ = two_users
    course = create_user_course(
        user["id"],
        CourseCreate(name="自动索引课程", goal="验证资料处理", daily_minutes=30),
    )
    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(
            title="等价类划分",
            content=(
                "等价类划分用于把输入域划分为有效等价类和无效等价类。"
                "边界值分析关注输入范围的边界及边界附近值。"
                "测试用例应覆盖每个有效类和无效类。"
            ),
        ),
    )

    result = process_material(
        user["id"],
        material["id"],
        embedding_provider=_fake_embeddings,
        knowledge_provider=_fake_knowledge_points,
    )

    completed = get_user_material(user["id"], material["id"])
    points = list_course_knowledge_points(user["id"], course["id"])
    updated_course = get_user_course(user["id"], course["id"])

    assert result["chunk_count"] >= 1
    assert result["knowledge_point_count"] == 3
    assert completed["processing_status"] == "ready"
    assert completed["parse_status"] == "parsed"
    assert completed["index_status"] == "ready"
    assert completed["processing_error"] is None
    assert len(points) == 3
    assert all(point["source_chunk_ids"] for point in points)
    assert updated_course["status"] == "diagnostic_pending"

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT embedding_json, embedding_model, embedding_hash,
                   chunker_version, estimated_tokens
            FROM course_material_chunks
            WHERE material_id = %s
            """,
            (material["id"],),
        )
        chunks = cursor.fetchall()
    assert chunks
    assert all(chunk["embedding_json"] for chunk in chunks)
    assert all(chunk["embedding_model"] for chunk in chunks)
    assert all(chunk["embedding_hash"] for chunk in chunks)
    assert all(chunk["chunker_version"] == "structure-token-v2" for chunk in chunks)
    assert all(0 < chunk["estimated_tokens"] <= 320 for chunk in chunks)


def test_material_delete_removes_chunks_and_owned_knowledge(api_client, two_users):
    user, other = two_users
    course = create_user_course(user["id"], CourseCreate(name="资料删除课程"))
    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(title="待删除讲义", content="用于验证资料删除后索引与知识点同步清理。"),
    )
    process_material(
        user["id"],
        material["id"],
        embedding_provider=_fake_embeddings,
        knowledge_provider=_fake_knowledge_points,
    )

    listed = api_client.get(f"/api/v1/courses/{course['id']}/materials")
    assert listed.status_code == 200
    assert listed.json()["data"]["items"][0]["created_at"]

    with pytest.raises(AppError) as forbidden:
        delete_user_material(other["id"], material["id"])
    assert forbidden.value.status_code == 404

    deleted = api_client.delete(f"/api/v1/materials/{material['id']}")
    assert deleted.status_code == 200
    assert deleted.json()["data"]["deleted"] is True
    assert deleted.json()["data"]["removed_chunk_count"] >= 1

    with get_cursor() as cursor:
        cursor.execute("SELECT COUNT(*) AS total FROM course_materials WHERE id = %s", (material["id"],))
        assert cursor.fetchone()["total"] == 0
        cursor.execute("SELECT COUNT(*) AS total FROM course_material_chunks WHERE material_id = %s", (material["id"],))
        assert cursor.fetchone()["total"] == 0
        cursor.execute(
            """
            SELECT COUNT(*) AS total FROM knowledge_points
            WHERE course_id = %s AND status = 'orphaned'
            """,
            (course["id"],),
        )
        assert cursor.fetchone()["total"] == 3


def test_knowledge_definition_summary_and_examples_are_vectorized(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="知识语义向量课程"))
    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(title="结构化知识点", content="这是一段用于建立课程片段向量的正文。"),
    )
    embedded_texts = []

    def capture_embeddings(texts):
        embedded_texts.extend(texts)
        return _fake_embeddings(texts)

    def structured_points(_course_name, _title, chunks):
        return [
            {
                "name": "语义字段知识点",
                "description": "定义字段标记",
                "summary": "摘要字段标记",
                "examples": ["例子字段标记"],
                "chunk_indices": [chunks[0]["chunk_index"]],
            }
        ]

    process_material(
        user["id"],
        material["id"],
        embedding_provider=capture_embeddings,
        knowledge_provider=structured_points,
    )
    vector_text = next(text for text in embedded_texts if "语义字段知识点" in text)
    assert "定义：定义字段标记" in vector_text
    assert "摘要：摘要字段标记" in vector_text
    assert "例子：例子字段标记" in vector_text

    point = list_course_knowledge_points(user["id"], course["id"])[0]
    assert point["summary"] == "摘要字段标记"
    assert point["examples"] == ["例子字段标记"]
    with get_cursor() as cursor:
        cursor.execute(
            "SELECT embedding_json FROM knowledge_points WHERE id = %s AND user_id = %s",
            (point["id"], user["id"]),
        )
        assert cursor.fetchone()["embedding_json"]


def test_knowledge_extraction_has_deterministic_fallback(monkeypatch):
    monkeypatch.setattr(
        knowledge_extractor,
        "get_llm",
        lambda: (_ for _ in ()).throw(RuntimeError("LLM unavailable")),
    )
    points = knowledge_extractor.extract_knowledge_points(
        "软件测试",
        "等价类划分",
        [
            {
                "chunk_index": 0,
                "chunk_text": "有效等价类表示符合需求的输入。无效等价类表示不符合约束的输入。",
            }
        ],
    )

    assert len(points) >= 3
    assert all(point["chunk_indices"] == [0] for point in points)


def test_mock_llm_skips_external_knowledge_extraction(monkeypatch):
    monkeypatch.setattr(
        knowledge_extractor,
        "get_settings",
        lambda: type("Settings", (), {"mock_llm": True})(),
    )
    monkeypatch.setattr(
        knowledge_extractor,
        "get_llm",
        lambda: (_ for _ in ()).throw(AssertionError("LLM must not be called")),
    )

    points = knowledge_extractor.extract_knowledge_points(
        "软件测试",
        "测试方法",
        [{"chunk_index": 0, "chunk_text": "等价类、边界值和判定表是常见测试设计方法。"}],
    )

    assert len(points) >= 3


def test_upload_stops_when_size_limit_is_exceeded(monkeypatch, tmp_path):
    monkeypatch.setattr(file_storage, "UPLOAD_ROOT", tmp_path.resolve())
    upload = UploadFile(
        file=BytesIO(b"x" * (file_storage.MAX_UPLOAD_SIZE + 1)),
        filename="oversized.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(ValueError, match="100MB"):
        asyncio.run(file_storage.save_upload(upload, user_id=999))

    assert list(tmp_path.rglob("*.txt")) == []


def test_supported_upload_is_streamed_to_local_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(file_storage, "UPLOAD_ROOT", tmp_path.resolve())
    upload = UploadFile(
        file=BytesIO("课程资料".encode("utf-8")),
        filename="material.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    stored = asyncio.run(file_storage.save_upload(upload, user_id=999))

    assert stored.size == len("课程资料".encode("utf-8"))
    assert file_storage.read_upload(stored.storage_path) == "课程资料".encode("utf-8")


def test_legacy_upload_reader_also_enforces_limit_in_chunks():
    class RecordingBytesIO(BytesIO):
        def __init__(self, value):
            super().__init__(value)
            self.requested_sizes = []

        def read(self, size=-1):
            self.requested_sizes.append(size)
            return super().read(size)

    stream = RecordingBytesIO(b"x" * (file_storage.MAX_UPLOAD_SIZE + 1))
    upload = UploadFile(
        file=stream,
        filename="legacy-oversized.txt",
        headers=Headers({"content-type": "text/plain"}),
    )

    with pytest.raises(ValueError, match="100MB"):
        asyncio.run(file_storage.read_limited_upload(upload))

    assert stream.requested_sizes
    assert set(stream.requested_sizes) == {file_storage.UPLOAD_CHUNK_SIZE}


def test_processing_failure_is_visible_and_retryable(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="失败状态课程"))
    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(title="失败资料", content="这是一段可以正常解析的文本资料。"),
    )

    def failed_embeddings(_texts):
        raise RuntimeError("embedding service unavailable")

    with pytest.raises(RuntimeError, match="embedding service unavailable"):
        process_material(
            user["id"],
            material["id"],
            embedding_provider=failed_embeddings,
            knowledge_provider=_fake_knowledge_points,
        )

    failed = get_user_material(user["id"], material["id"])
    assert failed["processing_status"] == "failed"
    assert failed["index_status"] == "failed"
    assert "embedding service unavailable" in failed["processing_error"]


def test_course_search_returns_standard_citations(api_client, two_users, monkeypatch):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="引用课程"))
    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(title="引用资料", content="青层表示符合需求说明的有效输入集合。"),
    )
    process_material(
        user["id"],
        material["id"],
        embedding_provider=_fake_embeddings,
        knowledge_provider=_fake_knowledge_points,
    )

    def fake_search(_query, chunks, _points, _top_k):
        return [
            {
                **chunks[0],
                "score": 0.91,
                "dense_score": 0.9,
                "keyword_score": 0.95,
                "knowledge_score": 0.8,
                "knowledge_points": [],
            }
        ]

    monkeypatch.setattr(materials_service, "hybrid_search", fake_search)
    response = api_client.post(
        f"/api/v1/courses/{course['id']}/materials/search",
        json={"query": "什么是青层", "top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["total"] == 1
    citation = payload["citations"][0]
    assert citation["chunk_id"]
    assert citation["material_id"] == material["id"]
    assert citation["material_title"] == "引用资料"
    assert citation["chunk_index"] == 0
    assert citation["score"] == 0.91
    assert citation["dense_score"] == 0.9
    assert citation["keyword_score"] == 0.95
    assert "青层" in citation["snippet"]
    assert payload["trace"]["trace_id"]
    assert payload["trace"]["candidate_chunks"] >= 1
    assert payload["trace"]["timings_ms"]["total"] >= 0
