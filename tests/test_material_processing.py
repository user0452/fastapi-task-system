import asyncio
import json
import shutil
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from pathlib import Path
from threading import Barrier, Event
from uuid import uuid4

import numpy as np
import pytest
from starlette.datastructures import Headers, UploadFile

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations import file_storage
from app.integrations.embedding import persistent_index
from app.integrations.file_storage import StoredUpload
from app.integrations.llm import knowledge_extractor
from app.jobs.material_index_job import enqueue_material_processing_job
from app.modules.courses.schemas import CourseCreate
from app.modules.courses.service import (
    archive_user_course,
    create_user_course,
    get_user_course,
    reconcile_course_after_material_processing,
)
from app.modules.materials import service as materials_service
from app.modules.materials.schemas import TextMaterialCreate
from app.modules.materials.service import (
    create_text_material,
    delete_user_material,
    get_user_material,
    list_course_knowledge_points,
    process_material,
    request_material_retry,
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


@pytest.mark.parametrize(
    ("initial_status", "has_enough_knowledge", "expected_status"),
    [
        ("draft", False, "preparing"),
        ("draft", True, "diagnostic_pending"),
        ("preparing", False, "preparing"),
        ("preparing", True, "diagnostic_pending"),
        ("diagnostic_pending", False, "diagnostic_pending"),
        ("diagnostic_pending", True, "diagnostic_pending"),
        ("active", False, "active"),
        ("active", True, "active"),
        ("completed", False, "completed"),
        ("completed", True, "completed"),
        ("archived", False, None),
        ("archived", True, None),
    ],
)
def test_material_processing_course_status_matrix(
    two_users,
    initial_status,
    has_enough_knowledge,
    expected_status,
):
    user, _ = two_users
    course = create_user_course(
        user["id"],
        CourseCreate(name=f"资料状态矩阵-{initial_status}-{has_enough_knowledge}"),
    )
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE courses SET status = %s WHERE id = %s AND user_id = %s",
            (initial_status, course["id"], user["id"]),
        )

    if expected_status is None:
        with pytest.raises(AppError) as error:
            with get_cursor() as cursor:
                reconcile_course_after_material_processing(
                    cursor,
                    user["id"],
                    course["id"],
                    has_enough_knowledge=has_enough_knowledge,
                )
        assert error.value.error_code == "ARCHIVED_COURSE_MATERIALS_FORBIDDEN"
    else:
        with get_cursor() as cursor:
            reconciled = reconcile_course_after_material_processing(
                cursor,
                user["id"],
                course["id"],
                has_enough_knowledge=has_enough_knowledge,
            )
        assert reconciled["status"] == expected_status

    assert get_user_course(user["id"], course["id"])["status"] == (
        initial_status if expected_status is None else expected_status
    )


@pytest.mark.parametrize("stable_status", ["active", "completed"])
def test_material_upload_processing_rebuild_and_delete_do_not_regress_course(
    two_users,
    stable_status,
):
    user, _ = two_users
    course = create_user_course(
        user["id"],
        CourseCreate(name=f"不回退课程-{stable_status}"),
    )
    with get_cursor() as cursor:
        cursor.execute(
            "UPDATE courses SET status = %s WHERE id = %s AND user_id = %s",
            (stable_status, course["id"], user["id"]),
        )

    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(title="不回退资料", content="用于验证资料操作不会回退课程状态。"),
    )
    assert get_user_course(user["id"], course["id"])["status"] == stable_status

    process_material(
        user["id"],
        material["id"],
        embedding_provider=_fake_embeddings,
        knowledge_provider=_fake_knowledge_points,
    )
    assert get_user_course(user["id"], course["id"])["status"] == stable_status

    delete_user_material(user["id"], material["id"])
    assert get_user_course(user["id"], course["id"])["status"] == stable_status


def test_archived_course_rejects_upload_retry_and_processing(
    api_client,
    two_users,
    monkeypatch,
):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="归档资料禁用课程"))
    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(title="归档前资料", content="归档后不得继续处理。"),
    )
    archive_user_course(user["id"], course["id"])

    with pytest.raises(AppError) as text_error:
        create_text_material(
            user["id"],
            course["id"],
            TextMaterialCreate(title="归档后资料", content="不应创建"),
        )
    assert text_error.value.error_code == "ARCHIVED_COURSE_MATERIALS_FORBIDDEN"

    with pytest.raises(AppError) as retry_error:
        request_material_retry(user["id"], material["id"])
    assert retry_error.value.error_code == "ARCHIVED_COURSE_MATERIALS_FORBIDDEN"

    with pytest.raises(AppError) as process_error:
        process_material(
            user["id"],
            material["id"],
            embedding_provider=_fake_embeddings,
            knowledge_provider=_fake_knowledge_points,
        )
    assert process_error.value.error_code == "ARCHIVED_COURSE_MATERIALS_FORBIDDEN"

    saved = False

    async def save_must_not_run(*_args, **_kwargs):
        nonlocal saved
        saved = True
        raise AssertionError("archived course must be rejected before file persistence")

    monkeypatch.setattr("app.modules.materials.router.save_upload", save_must_not_run)
    response = api_client.post(
        f"/api/v1/courses/{course['id']}/materials/upload",
        data={"title": "归档后上传"},
        files={"file": ("material.txt", b"content", "text/plain")},
    )
    assert response.status_code == 409
    assert response.json()["error_code"] == "ARCHIVED_COURSE_MATERIALS_FORBIDDEN"
    assert saved is False


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
        cursor.execute(
            """
            SELECT processing_status, storage_path
            FROM course_materials WHERE id = %s
            """,
            (material["id"],),
        )
        tombstone = cursor.fetchone()
        assert tombstone["processing_status"] == "deleted"
        assert tombstone["storage_path"] is None
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

    repeated = api_client.delete(f"/api/v1/materials/{material['id']}")
    assert repeated.status_code == 200
    assert repeated.json()["data"]["deleted"] is True
    assert repeated.json()["data"]["already_deleted"] is True


def test_uploaded_file_is_removed_when_database_insert_fails(two_users, monkeypatch, tmp_path):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="上传回滚课程"))
    monkeypatch.setattr(file_storage, "UPLOAD_ROOT", tmp_path.resolve())
    user_dir = tmp_path / str(user["id"])
    user_dir.mkdir(parents=True)
    stored_path = user_dir / "db-failure.txt"
    stored_path.write_text("待回滚文件", encoding="utf-8")
    upload = StoredUpload(
        original_filename="db-failure.txt",
        storage_path=str(stored_path),
        mime_type="text/plain",
        size=stored_path.stat().st_size,
    )

    monkeypatch.setattr(
        materials_service.repository,
        "create_file_material",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("database insert failed")),
    )

    with pytest.raises(RuntimeError, match="database insert failed"):
        materials_service.create_uploaded_material(
            user["id"],
            course["id"],
            "数据库失败资料",
            upload,
        )
    assert not stored_path.exists()


def test_upload_validates_course_before_saving_file(api_client, monkeypatch):
    saved = False

    async def save_must_not_run(*args, **kwargs):
        nonlocal saved
        saved = True
        raise AssertionError("file must not be saved before course ownership validation")

    monkeypatch.setattr("app.modules.materials.router.save_upload", save_must_not_run)
    response = api_client.post(
        "/api/v1/courses/2147483647/materials/upload",
        data={"title": "越权上传"},
        files={"file": ("material.txt", b"content", "text/plain")},
    )

    assert response.status_code == 404
    assert saved is False


def test_delete_recovers_after_index_rebuild_failure(two_users, monkeypatch, tmp_path):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="删除恢复课程"))
    monkeypatch.setattr(file_storage, "UPLOAD_ROOT", tmp_path.resolve())
    user_dir = tmp_path / str(user["id"])
    user_dir.mkdir(parents=True)
    stored_path = user_dir / "recoverable-delete.txt"
    stored_path.write_text("可恢复删除资料正文", encoding="utf-8")
    material = materials_service.create_uploaded_material(
        user["id"],
        course["id"],
        "可恢复删除资料",
        StoredUpload(
            original_filename=stored_path.name,
            storage_path=str(stored_path),
            mime_type="text/plain",
            size=stored_path.stat().st_size,
        ),
    )
    process_material(
        user["id"],
        material["id"],
        embedding_provider=_fake_embeddings,
        knowledge_provider=_fake_knowledge_points,
    )
    enqueue_material_processing_job(user["id"], course["id"], material["id"])
    real_rebuild = materials_service._rebuild_vector_index
    monkeypatch.setattr(
        materials_service,
        "_rebuild_vector_index",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("index rebuild failed")),
    )

    with pytest.raises(AppError) as failed:
        delete_user_material(user["id"], material["id"])
    assert failed.value.error_code == "MATERIAL_DELETE_RETRYABLE"
    assert stored_path.exists()

    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT processing_status, index_status
            FROM course_materials WHERE id = %s
            """,
            (material["id"],),
        )
        failed_material = cursor.fetchone()
        assert failed_material == {"processing_status": "delete_failed", "index_status": "failed"}
        cursor.execute(
            "SELECT COUNT(*) AS total FROM course_material_chunks WHERE material_id = %s",
            (material["id"],),
        )
        assert cursor.fetchone()["total"] == 0
        cursor.execute(
            "SELECT status FROM material_processing_jobs WHERE material_id = %s",
            (material["id"],),
        )
        assert cursor.fetchone()["status"] == "cancelled"

    monkeypatch.setattr(materials_service, "_rebuild_vector_index", real_rebuild)
    recovered = delete_user_material(user["id"], material["id"])
    assert recovered["deleted"] is True
    assert not stored_path.exists()
    repeated = delete_user_material(user["id"], material["id"])
    assert repeated["already_deleted"] is True


def test_deleting_material_invalidates_inflight_processing(two_users):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="处理中删除课程"))
    material = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(title="处理中资料", content="这是一段正在生成向量的资料内容。"),
    )
    embedding_started = Event()
    release_embedding = Event()

    def slow_embeddings(texts):
        embedding_started.set()
        assert release_embedding.wait(timeout=10)
        return _fake_embeddings(texts)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            process_material,
            user["id"],
            material["id"],
            slow_embeddings,
            _fake_knowledge_points,
        )
        assert embedding_started.wait(timeout=10)
        deleted = delete_user_material(user["id"], material["id"])
        assert deleted["deleted"] is True
        release_embedding.set()
        with pytest.raises(materials_service.MaterialProcessingCancelled):
            future.result(timeout=20)

    with get_cursor() as cursor:
        cursor.execute(
            "SELECT processing_status FROM course_materials WHERE id = %s",
            (material["id"],),
        )
        assert cursor.fetchone()["processing_status"] == "deleted"
        cursor.execute(
            "SELECT COUNT(*) AS total FROM course_material_chunks WHERE material_id = %s",
            (material["id"],),
        )
        assert cursor.fetchone()["total"] == 0


def test_concurrent_material_indexing_keeps_both_materials(
    two_users,
    monkeypatch,
):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="并发索引课程"))
    first = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(title="并发资料一", content="第一份并发索引资料。"),
    )
    second = create_text_material(
        user["id"],
        course["id"],
        TextMaterialCreate(title="并发资料二", content="第二份并发索引资料。"),
    )
    index_root = (
        Path.cwd()
        / "var"
        / "test-rag-indexes"
        / uuid4().hex
    ).resolve()
    index_root.mkdir(parents=True)
    monkeypatch.setattr(persistent_index, "INDEX_ROOT", index_root)
    embedding_barrier = Barrier(2)

    def concurrent_embeddings(texts):
        embedding_barrier.wait(timeout=15)
        return _fake_embeddings(texts)

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    process_material,
                    user["id"],
                    material_id,
                    concurrent_embeddings,
                    _fake_knowledge_points,
                )
                for material_id in (first["id"], second["id"])
            ]
            results = [future.result(timeout=30) for future in futures]

        metadata_path = (
            index_root
            / str(user["id"])
            / f"course-{course['id']}.json"
        )
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        assert metadata["count"] == 2
        assert metadata["generation"] > 0
        assert metadata["index_version"] == persistent_index.INDEX_FORMAT_VERSION
        assert max(result["vector_index_count"] for result in results) == 2
    finally:
        shutil.rmtree(index_root, ignore_errors=True)


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

    def fake_search(_query, chunks, _points, _top_k, **_kwargs):
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


def test_rag_candidate_sources_keep_independent_quotas(two_users, monkeypatch):
    user, _ = two_users
    course = create_user_course(user["id"], CourseCreate(name="候选融合课程"))
    query = "独有关键词"
    embedding_calls = []
    captured_ids = []

    def counted_embeddings(texts):
        embedding_calls.append(list(texts))
        return np.tile(np.array([[1.0, 0.0]], dtype="float32"), (len(texts), 1))

    point = {
        "id": 500,
        "name": query,
        "description": "知识点主动召回",
        "summary": "",
        "examples": [],
        "source_chunk_ids": [777],
        "embedding_json": json.dumps([1.0, 0.0]),
        "extraction_confidence": 1.0,
        "status": "active",
    }

    monkeypatch.setattr(materials_service, "embed_texts", counted_embeddings)
    monkeypatch.setattr(
        materials_service.repository,
        "count_course_search_terms",
        lambda *_args: 1,
    )
    monkeypatch.setattr(
        materials_service.repository,
        "keyword_candidate_ids",
        lambda *_args: [999],
    )
    monkeypatch.setattr(
        materials_service.repository,
        "list_knowledge_points",
        lambda *_args: [point],
    )
    monkeypatch.setattr(
        materials_service,
        "vector_candidates",
        lambda *_args: [(chunk_id, 1.0) for chunk_id in range(1, 41)],
    )

    def chunks_by_ids(_cursor, _course_id, _user_id, ids):
        return [
            {
                "id": chunk_id,
                "material_id": 1,
                "material_title": "候选资料",
                "filename": "candidate.txt",
                "chunk_index": index,
                "chunk_text": f"候选 {chunk_id}",
                "embedding_json": json.dumps([1.0, 0.0]),
                "kb_ids": [],
            }
            for index, chunk_id in enumerate(ids)
        ]

    monkeypatch.setattr(
        materials_service.repository,
        "get_course_chunks_by_ids",
        chunks_by_ids,
    )

    def capture_search(_query, chunks, _points, _top_k, **kwargs):
        captured_ids.extend(chunk["id"] for chunk in chunks)
        assert kwargs["precomputed_query_embeddings"] is not None
        return []

    monkeypatch.setattr(materials_service, "hybrid_search", capture_search)

    result = materials_service.search_course_materials(
        user["id"],
        course["id"],
        query,
        top_k=5,
    )

    assert 999 in captured_ids
    assert 777 in captured_ids
    assert result["trace"]["vector_candidates"] == 40
    assert result["trace"]["keyword_candidates"] == 1
    assert result["trace"]["knowledge_candidates"] == 1
    assert embedding_calls == [[query]]
