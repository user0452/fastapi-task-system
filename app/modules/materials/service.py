import hashlib
import json
from collections import Counter
from contextlib import suppress
from time import perf_counter
from typing import Callable
from uuid import uuid4

from app.core.database import get_cursor
from app.core.errors import AppError
from app.integrations.document_parser import extract_text_from_path
from app.integrations.embedding.chunking import (
    CHUNKER_VERSION,
    chunk_document,
    estimate_tokens,
    retrieval_text,
)
from app.integrations.embedding.hybrid_search import (
    DEFAULT_ENABLE_MULTI_QUERY,
    RERANKER_VERSION,
    RETRIEVER_VERSION,
    build_query_variants,
    hybrid_search,
    tokenize_for_search,
)
from app.integrations.embedding.persistent_index import (
    rebuild_course_vector_index,
    vector_candidates,
)
from app.integrations.embedding.service import (
    EMBEDDING_MODEL_NAME,
    embed_texts,
    serialize_embedding,
)
from app.integrations.file_storage import StoredUpload, resolve_upload_path
from app.integrations.llm.knowledge_extractor import extract_knowledge_structure
from app.modules.audit.service import record_audit
from app.modules.courses.service import get_user_course
from app.modules.materials import repository
from app.modules.materials.schemas import TextMaterialCreate

RAG_EVIDENCE_MAX_TOKENS = 9_000
RAG_SECTION_MAX_TOKENS = 6_000
RAG_EVIDENCE_BLOCK_MAX_TOKENS = 1_800
RAG_MAX_ANCHORS = 10
RAG_MAX_NEIGHBOR_WINDOW = 2


def get_course_material_chunk(user_id: int, course_id: int, chunk_id: int) -> dict:
    """Return the complete, access-controlled source text behind one citation."""
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        chunk = repository.get_course_chunk(cursor, course_id, chunk_id, user_id)
    if chunk is None:
        raise AppError("资料片段不存在或无访问权限", 404, "MATERIAL_CHUNK_NOT_FOUND")
    return chunk


def _chunk_token_count(chunk: dict) -> int:
    return int(chunk.get("estimated_tokens") or estimate_tokens(chunk.get("chunk_text") or ""))


def _build_evidence_blocks(
    chunks: list[dict],
    anchor_ids: list[int],
    *,
    neighbor_window: int,
    max_tokens: int,
) -> dict:
    """Expand anchor chunks and merge contiguous evidence under a hard token budget."""
    by_id = {int(chunk["id"]): chunk for chunk in chunks}
    by_material: dict[int, list[dict]] = {}
    for chunk in chunks:
        by_material.setdefault(int(chunk["material_id"]), []).append(chunk)
    for material_chunks in by_material.values():
        material_chunks.sort(key=lambda item: (int(item["chunk_index"]), int(item["id"])))

    anchor_ids = list(dict.fromkeys(int(value) for value in anchor_ids))[:RAG_MAX_ANCHORS]
    anchor_set = {chunk_id for chunk_id in anchor_ids if chunk_id in by_id}
    selected: dict[int, dict] = {}
    for anchor_id in anchor_ids:
        anchor = by_id.get(anchor_id)
        if anchor is None:
            continue
        material_chunks = by_material[int(anchor["material_id"])]
        for chunk in material_chunks:
            if abs(int(chunk["chunk_index"]) - int(anchor["chunk_index"])) <= neighbor_window:
                selected[int(chunk["id"])] = chunk

    ordered = sorted(
        selected.values(),
        key=lambda item: (int(item["material_id"]), int(item["chunk_index"]), int(item["id"])),
    )
    grouped: list[list[dict]] = []
    pending: list[dict] = []
    pending_tokens = 0
    for chunk in ordered:
        chunk_tokens = _chunk_token_count(chunk)
        compatible = (
            not pending
            or (
                int(pending[-1]["material_id"]) == int(chunk["material_id"])
                and int(chunk["chunk_index"]) == int(pending[-1]["chunk_index"]) + 1
                and (pending[-1].get("heading_path") or "") == (chunk.get("heading_path") or "")
                and pending_tokens + chunk_tokens <= RAG_EVIDENCE_BLOCK_MAX_TOKENS
            )
        )
        if not compatible:
            grouped.append(pending)
            pending = []
            pending_tokens = 0
        pending.append(chunk)
        pending_tokens += chunk_tokens
    if pending:
        grouped.append(pending)

    blocks: list[dict] = []
    used_tokens = 0
    included_chunk_ids: set[int] = set()
    for group in grouped:
        token_count = sum(_chunk_token_count(chunk) for chunk in group)
        if blocks and used_tokens + token_count > max_tokens:
            break
        if token_count > max_tokens:
            group = group[:1]
            token_count = _chunk_token_count(group[0])
        if used_tokens + token_count > max_tokens:
            break
        included_chunk_ids.update(int(chunk["id"]) for chunk in group)
        used_tokens += token_count
        headings = list(dict.fromkeys(chunk.get("heading_path") for chunk in group if chunk.get("heading_path")))
        pages = [int(chunk["page_number"]) for chunk in group if chunk.get("page_number") is not None]
        blocks.append(
            {
                "material_id": int(group[0]["material_id"]),
                "material_title": group[0].get("material_title"),
                "filename": group[0].get("filename"),
                "heading_path": headings[0] if len(headings) == 1 else headings,
                "page_start": min(pages) if pages else None,
                "page_end": max(pages) if pages else None,
                "chunk_ids": [int(chunk["id"]) for chunk in group],
                "anchor_chunk_ids": [int(chunk["id"]) for chunk in group if int(chunk["id"]) in anchor_set],
                "estimated_tokens": token_count,
                "evidence_text": "\n\n".join(
                    f"[chunk_id={chunk['id']}] {chunk['chunk_text']}" for chunk in group
                ),
            }
        )
    return {
        "evidence_blocks": blocks,
        "used_tokens": used_tokens,
        "max_tokens": max_tokens,
        "anchor_chunk_ids": sorted(anchor_set),
        "included_chunk_ids": sorted(included_chunk_ids),
        "truncated": len(included_chunk_ids) < len(selected),
    }


def get_course_evidence_context(
    user_id: int,
    course_id: int,
    chunk_ids: list[int],
    neighbor_window: int = 1,
    max_tokens: int = RAG_EVIDENCE_MAX_TOKENS,
) -> dict:
    get_user_course(user_id, course_id)
    window = max(0, min(int(neighbor_window), RAG_MAX_NEIGHBOR_WINDOW))
    budget = max(500, min(int(max_tokens), RAG_EVIDENCE_MAX_TOKENS))
    with get_cursor() as cursor:
        chunks = repository.get_course_neighbor_chunks(
            cursor, course_id, user_id, chunk_ids, window
        )
    result = _build_evidence_blocks(
        chunks,
        chunk_ids,
        neighbor_window=window,
        max_tokens=budget,
    )
    result.update({"course_id": course_id, "neighbor_window": window})
    return result


def list_course_material_outline(
    user_id: int,
    course_id: int,
    material_id: int | None = None,
) -> dict:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        rows = repository.list_course_outline_rows(
            cursor, course_id, user_id, material_id
        )

    materials: dict[int, dict] = {}
    for row in rows:
        current = materials.setdefault(
            int(row["material_id"]),
            {
                "material_id": int(row["material_id"]),
                "material_title": row.get("material_title"),
                "filename": row.get("filename"),
                "sections": [],
            },
        )
        current["sections"].append(
            {
                "heading_path": row.get("heading_path") or "未命名章节",
                "chunk_count": int(row["chunk_count"]),
                "estimated_tokens": int(row["estimated_tokens"]),
                "first_chunk_id": int(row["first_chunk_id"]),
                "page_start": row.get("page_start"),
                "page_end": row.get("page_end"),
            },
        )

    items = []
    for material in materials.values():
        material["estimated_tokens"] = sum(section["estimated_tokens"] for section in material["sections"])
        items.append(material)
    return {"course_id": course_id, "materials": items, "total": len(items)}


def read_course_material_section(
    user_id: int,
    course_id: int,
    material_id: int,
    heading_path: str,
    max_tokens: int = RAG_SECTION_MAX_TOKENS,
) -> dict:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        matches = repository.get_course_section_chunks(
            cursor, course_id, user_id, material_id, heading_path
        )
    if not matches:
        raise AppError("未找到指定资料章节", 404, "MATERIAL_SECTION_NOT_FOUND")
    result = _build_evidence_blocks(
        matches,
        [int(chunk["id"]) for chunk in matches],
        neighbor_window=0,
        max_tokens=max(500, min(int(max_tokens), RAG_SECTION_MAX_TOKENS)),
    )
    result.update(
        {
            "course_id": course_id,
            "material_id": material_id,
            "requested_heading": heading_path,
            "matched_headings": list(dict.fromkeys(chunk.get("heading_path") or "未命名章节" for chunk in matches)),
        }
    )
    return result


def _split_document(text: str) -> list[dict]:
    return chunk_document(text)


def _knowledge_vector_text(point: dict) -> str:
    examples = [str(item).strip() for item in (point.get("examples") or []) if str(item).strip()]
    return "\n".join(
        part
        for part in [
            f"名称：{point.get('name', '')}",
            f"定义：{point.get('description', '')}",
            f"摘要：{point.get('summary', '')}",
            f"例子：{'；'.join(examples)}" if examples else "",
        ]
        if part and not part.endswith("：")
    ).strip()


def _search_terms_for_chunk(chunk: dict, material_title: str) -> dict:
    text = retrieval_text(
        chunk.get("chunk_text") or "",
        chunk.get("heading_path"),
        chunk.get("kb_ids"),
        material_title,
    )
    terms = tokenize_for_search(text)
    return {
        "id": int(chunk["id"]),
        "term_frequencies": dict(Counter(terms)),
        "document_length": len(terms),
    }


def _rebuild_vector_index(user_id: int, course_id: int) -> int:
    with get_cursor() as cursor:
        rows = repository.list_course_vector_rows(cursor, course_id, user_id)
    return rebuild_course_vector_index(
        user_id,
        course_id,
        rows,
        embedding_model=EMBEDDING_MODEL_NAME,
    )


def create_text_material(user_id: int, course_id: int, request: TextMaterialCreate) -> dict:
    course = get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        material = repository.create_text_material(
            cursor,
            user_id,
            course,
            request.title,
            request.content,
        )
        record_audit(
            user_id,
            "COURSE_MATERIAL_CREATED",
            "material",
            material["id"],
            {"course_id": course_id, "kind": "text"},
            cursor=cursor,
        )
        return material


def create_uploaded_material(
    user_id: int,
    course_id: int,
    title: str,
    upload: StoredUpload,
) -> dict:
    course = get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        material = repository.create_file_material(cursor, user_id, course, title, upload)
        record_audit(
            user_id,
            "COURSE_MATERIAL_CREATED",
            "material",
            material["id"],
            {"course_id": course_id, "kind": "file", "size": upload.size},
            cursor=cursor,
        )
        return material


def get_user_material(user_id: int, material_id: int) -> dict:
    with get_cursor() as cursor:
        material = repository.get_material(cursor, material_id, user_id)
        if material is None:
            raise AppError("资料不存在或无访问权限", 404, "MATERIAL_NOT_FOUND")
        record_audit(
            user_id,
            "COURSE_MATERIAL_VIEWED",
            "material",
            material_id,
            {"course_id": material.get("course_id")},
            cursor=cursor,
        )
        return material


def delete_user_material(user_id: int, material_id: int) -> dict:
    with get_cursor() as cursor:
        result = repository.delete_material(cursor, material_id, user_id)
        if result is None:
            raise AppError("资料不存在或无访问权限", 404, "MATERIAL_NOT_FOUND")
        material = result["material"]
        record_audit(
            user_id,
            "COURSE_MATERIAL_DELETED",
            "material",
            material_id,
            {
                "course_id": material.get("course_id"),
                "removed_chunk_count": result["removed_chunk_count"],
                "removed_knowledge_point_count": len(result["removed_knowledge_point_ids"]),
                "orphaned_knowledge_point_count": len(result.get("orphaned_knowledge_point_ids", [])),
            },
            cursor=cursor,
        )

    _rebuild_vector_index(user_id, material["course_id"])

    storage_path = material.get("storage_path")
    if storage_path:
        with suppress(OSError, ValueError):
            resolve_upload_path(storage_path).unlink(missing_ok=True)

    return {
        "id": material_id,
        "course_id": material.get("course_id"),
        "title": material.get("title"),
        "deleted": True,
        "removed_chunk_count": result["removed_chunk_count"],
        "removed_knowledge_point_count": len(result["removed_knowledge_point_ids"]),
        "orphaned_knowledge_point_count": len(result.get("orphaned_knowledge_point_ids", [])),
    }


def request_material_retry(user_id: int, material_id: int) -> dict:
    material = get_user_material(user_id, material_id)
    material = _update_material(
        user_id,
        material_id,
        processing_status="uploaded",
        index_status="pending",
        processing_error=None,
    )
    record_audit(
        user_id,
        "COURSE_MATERIAL_RETRY_REQUESTED",
        "material",
        material_id,
        {"course_id": material.get("course_id")},
    )
    return material


def material_public_view(material: dict) -> dict:
    visible = dict(material)
    content = visible.pop("content", "") or ""
    visible.pop("storage_path", None)
    visible["content_preview"] = content[:300]
    return visible


def list_user_course_materials(user_id: int, course_id: int) -> list[dict]:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        items = repository.list_course_materials(cursor, course_id, user_id)
        record_audit(
            user_id,
            "COURSE_MATERIALS_LISTED",
            "course",
            course_id,
            {"count": len(items)},
            cursor=cursor,
        )
        return items


def list_course_knowledge_points(user_id: int, course_id: int) -> list[dict]:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        items = repository.list_knowledge_points(cursor, course_id, user_id)
        record_audit(
            user_id,
            "COURSE_KNOWLEDGE_VIEWED",
            "course",
            course_id,
            {"count": len(items)},
            cursor=cursor,
        )
    return [
        {
            key: value
            for key, value in point.items()
            if key not in {"embedding_json", "embedding_hash"}
        }
        for point in items
    ]


def get_course_knowledge_graph(user_id: int, course_id: int) -> dict:
    get_user_course(user_id, course_id)
    with get_cursor() as cursor:
        points = repository.list_knowledge_points(cursor, course_id, user_id)
        relations = repository.list_knowledge_point_relations(cursor, course_id, user_id)
        record_audit(
            user_id,
            "COURSE_KNOWLEDGE_GRAPH_VIEWED",
            "course",
            course_id,
            {"point_count": len(points), "relation_count": len(relations)},
            cursor=cursor,
        )
    return {
        "course_id": course_id,
        "points": [
            {
                key: value
                for key, value in point.items()
                if key not in {"embedding_json", "embedding_hash"}
            }
            for point in points
        ],
        "relations": relations,
    }


def _update_material(user_id: int, material_id: int, **changes) -> dict:
    with get_cursor() as cursor:
        material = repository.update_material(cursor, material_id, user_id, **changes)
        if material is None:
            raise AppError("资料不存在或无访问权限", 404, "MATERIAL_NOT_FOUND")
        return material


def _hash_file(path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            digest.update(block)
    return digest.hexdigest()


def process_material(
    user_id: int,
    material_id: int,
    embedding_provider: Callable = embed_texts,
    knowledge_provider: Callable = extract_knowledge_structure,
    heartbeat: Callable[[], None] | None = None,
) -> dict:
    material = get_user_material(user_id, material_id)
    renew_lease = heartbeat or (lambda: None)

    try:
        renew_lease()
        content = material.get("content") or ""
        if material.get("storage_path"):
            _update_material(
                user_id,
                material_id,
                processing_status="parsing",
                parse_status="parsing",
                processing_error=None,
            )
            source_path = resolve_upload_path(material["storage_path"])
            content = extract_text_from_path(source_path, material.get("filename") or source_path.name)
            material = _update_material(
                user_id,
                material_id,
                content=content,
                file_hash=_hash_file(source_path),
                parse_status="parsed",
            )
            renew_lease()

        if not content.strip():
            raise ValueError("资料内容为空，无法构建索引")

        if not material.get("file_hash"):
            material = _update_material(
                user_id,
                material_id,
                file_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )

        _update_material(
            user_id,
            material_id,
            processing_status="indexing",
            index_status="indexing",
            processing_error=None,
        )
        chunks = _split_document(content)
        if not chunks:
            raise ValueError("资料没有可索引的文本片段")

        for chunk in chunks:
            chunk["content_hash"] = hashlib.sha256(chunk["chunk_text"].encode("utf-8")).hexdigest()
            chunk["embedding_text"] = retrieval_text(
                chunk["chunk_text"],
                chunk.get("heading_path"),
                chunk.get("kb_ids"),
                material.get("title"),
            )
            chunk["embedding_hash"] = hashlib.sha256(
                (
                    f"{EMBEDDING_MODEL_NAME}\0{chunk['chunker_version']}\0"
                    f"{chunk['embedding_text']}"
                ).encode("utf-8")
            ).hexdigest()
        with get_cursor() as cursor:
            existing_chunks = repository.get_material_chunks(cursor, material_id, user_id)
        reusable_embeddings: dict[str, list[dict]] = {}
        for item in existing_chunks:
            if item.get("embedding_hash") and item.get("embedding_json"):
                reusable_embeddings.setdefault(item["embedding_hash"], []).append(item)

        prepared: list[dict] = []
        pending: list[tuple[int, dict]] = []
        reused_chunk_count = 0
        for index, chunk in enumerate(chunks):
            matches = reusable_embeddings.get(chunk["embedding_hash"], [])
            reusable = matches.pop(0) if matches else None
            if reusable:
                prepared.append(
                    {
                        **chunk,
                        "embedding_json": reusable["embedding_json"],
                        "embedding_model": reusable.get("embedding_model") or EMBEDDING_MODEL_NAME,
                    }
                )
                reused_chunk_count += 1
            else:
                prepared.append(dict(chunk))
                pending.append((index, chunk))

        if pending:
            embeddings = embedding_provider([chunk["embedding_text"] for _, chunk in pending])
            if len(embeddings) != len(pending):
                raise ValueError("Embedding 数量与新增资料片段数量不一致")
            for (index, _), embedding in zip(pending, embeddings):
                prepared[index]["embedding_json"] = serialize_embedding(embedding)
                prepared[index]["embedding_model"] = EMBEDDING_MODEL_NAME
        renew_lease()

        with get_cursor() as cursor:
            reloaded_material = repository.get_material(cursor, material_id, user_id)
            if reloaded_material is None:
                raise AppError("Material no longer exists", 404, "MATERIAL_NOT_FOUND")
            material = reloaded_material
            stored_chunks = repository.replace_chunks(cursor, material, prepared)
        renew_lease()

        extraction = knowledge_provider(
            material["course_name"],
            material["title"],
            stored_chunks,
        )
        if isinstance(extraction, dict):
            extracted = list(extraction.get("knowledge_points") or [])
            extracted_relations = list(extraction.get("relations") or [])
        else:
            extracted = list(extraction or [])
            extracted_relations = []
        renew_lease()
        index_to_id = {chunk["chunk_index"]: chunk["id"] for chunk in stored_chunks}
        points = []
        for point in extracted:
            source_ids = [
                index_to_id[index]
                for index in point.get("chunk_indices", [])
                if index in index_to_id
            ]
            points.append(
                {
                    "name": point["name"],
                    "description": point.get("description", ""),
                    "summary": point.get("summary", ""),
                    "examples": [
                        str(example).strip()[:300]
                        for example in point.get("examples", [])[:5]
                        if str(example).strip()
                    ],
                    "source_chunk_ids": source_ids,
                    "knowledge_level": point.get("knowledge_level", "concept"),
                    "category": point.get("category"),
                    "parent_name": point.get("parent_name"),
                    "confidence": float(point.get("confidence", 0.8)),
                }
            )
        relations = []
        for relation in extracted_relations:
            evidence_index = relation.get("evidence_chunk_index")
            relations.append(
                {
                    **relation,
                    "evidence_chunk_id": index_to_id.get(evidence_index),
                }
            )

        with get_cursor() as cursor:
            existing_points = repository.list_knowledge_points(cursor, material["course_id"], user_id)
        existing_by_name = {point["name"]: point for point in existing_points}
        point_pending: list[tuple[int, str]] = []
        reused_point_count = 0
        for index, point in enumerate(points):
            vector_text = _knowledge_vector_text(point)
            vector_hash = hashlib.sha256(
                f"{EMBEDDING_MODEL_NAME}\0knowledge-v1\0{vector_text}".encode("utf-8")
            ).hexdigest()
            point["embedding_hash"] = vector_hash
            existing = existing_by_name.get(point["name"])
            if (
                existing
                and existing.get("embedding_hash") == vector_hash
                and existing.get("embedding_json")
            ):
                point["embedding_json"] = existing["embedding_json"]
                point["embedding_model"] = existing.get("embedding_model") or EMBEDDING_MODEL_NAME
                reused_point_count += 1
            else:
                point_pending.append((index, vector_text))
        if point_pending:
            point_embeddings = embedding_provider([text for _, text in point_pending])
            if len(point_embeddings) != len(point_pending):
                raise ValueError("Embedding 数量与知识点数量不一致")
            for (index, _), embedding in zip(point_pending, point_embeddings):
                points[index]["embedding_json"] = serialize_embedding(embedding)
                points[index]["embedding_model"] = EMBEDDING_MODEL_NAME
        renew_lease()

        with get_cursor() as cursor:
            stored_points = repository.upsert_knowledge_points(
                cursor,
                user_id,
                material["course_id"],
                points,
            )
            repository.upsert_evidence_backed_relations(
                cursor,
                user_id,
                material["course_id"],
                stored_points,
                relations,
            )
            repository.replace_material_search_terms(
                cursor,
                user_id,
                material["course_id"],
                material_id,
                [_search_terms_for_chunk(chunk, material["title"]) for chunk in stored_chunks],
            )
            repository.set_course_status(
                cursor,
                material["course_id"],
                user_id,
                "diagnostic_pending" if len(points) >= 3 else "preparing",
            )
            completed = repository.update_material(
                cursor,
                material_id,
                user_id,
                processing_status="ready",
                parse_status="parsed",
                index_status="ready",
                processing_error=None,
                chunker_version=CHUNKER_VERSION,
            )
            record_audit(
                user_id,
                "COURSE_MATERIAL_INDEXED",
                "material",
                material_id,
                {
                    "course_id": material["course_id"],
                    "chunk_count": len(stored_chunks),
                    "reused_chunk_embeddings": reused_chunk_count,
                    "knowledge_point_count": len(points),
                    "reused_point_embeddings": reused_point_count,
                },
                cursor=cursor,
            )

        vector_index_count = _rebuild_vector_index(user_id, material["course_id"])

        return {
            "material": completed,
            "chunk_count": len(stored_chunks),
            "knowledge_point_count": len(points),
            "reused_chunk_embeddings": reused_chunk_count,
            "reused_knowledge_point_embeddings": reused_point_count,
            "vector_index_count": vector_index_count,
        }
    except Exception as exc:
        _update_material(
            user_id,
            material_id,
            processing_status="failed",
            index_status="failed",
            processing_error=str(exc)[:2000],
        )
        record_audit(
            user_id,
            "COURSE_MATERIAL_INDEX_FAILED",
            "material",
            material_id,
            {"error": str(exc)[:500]},
        )
        raise


def search_course_materials(user_id: int, course_id: int, query: str, top_k: int = 5) -> dict:
    total_started = perf_counter()
    course = get_user_course(user_id, course_id)
    load_started = perf_counter()
    candidate_limit = max(60, min(160, int(top_k) * 12))
    query_variants = build_query_variants(query) if DEFAULT_ENABLE_MULTI_QUERY else [query.strip()]
    query_variants = [value for value in query_variants if value]
    query_embeddings = embed_texts(query_variants)
    with get_cursor() as cursor:
        if repository.count_course_search_terms(cursor, user_id, course_id) == 0:
            legacy_rows = repository.get_course_search_rows(cursor, course_id, user_id)
            by_material: dict[int, list[dict]] = {}
            for row in legacy_rows:
                by_material.setdefault(int(row["material_id"]), []).append(row)
            for material_id, rows in by_material.items():
                repository.replace_material_search_terms(
                    cursor,
                    user_id,
                    course_id,
                    material_id,
                    [_search_terms_for_chunk(row, row.get("material_title") or "") for row in rows],
                )
        keyword_ids = repository.keyword_candidate_ids(
            cursor,
            user_id,
            course_id,
            [term for variant in query_variants for term in tokenize_for_search(variant)],
            candidate_limit,
        )
    vector_hits = vector_candidates(
        user_id, course_id, query_embeddings, candidate_limit
    )
    if not vector_hits:
        _rebuild_vector_index(user_id, course_id)
        vector_hits = vector_candidates(
            user_id, course_id, query_embeddings, candidate_limit
        )
    candidate_ids = list(
        dict.fromkeys([chunk_id for chunk_id, _score in vector_hits] + keyword_ids)
    )[:candidate_limit]
    with get_cursor() as cursor:
        chunks = repository.get_course_chunks_by_ids(cursor, course_id, user_id, candidate_ids)
        points = repository.list_knowledge_points_for_chunks(
            cursor, course_id, user_id, candidate_ids
        )
    load_ms = (perf_counter() - load_started) * 1000
    ranking_started = perf_counter()
    results = hybrid_search(query, chunks, points, top_k)
    ranking_ms = (perf_counter() - ranking_started) * 1000
    citations = [
        {
            "chunk_id": item["id"],
            "material_id": item["material_id"],
            "material_title": item["material_title"],
            "filename": item.get("filename"),
            "page_number": item.get("page_number"),
            "heading_path": item.get("heading_path"),
            "kb_ids": item.get("kb_ids", []),
            "document_type": item.get("document_type", "content"),
            "char_start": item.get("char_start"),
            "char_end": item.get("char_end"),
            "chunk_index": item["chunk_index"],
            "score": item["score"],
            "dense_score": item["dense_score"],
            "keyword_score": item["keyword_score"],
            "knowledge_score": item["knowledge_score"],
            "dense_rank": item.get("dense_rank"),
            "keyword_rank": item.get("keyword_rank"),
            "rrf_score": item.get("rrf_score"),
            "selection_score": item.get("selection_score", item["score"]),
            "evidence_overlap": item.get("evidence_overlap", 0),
            "coverage_penalty": item.get("coverage_penalty", 0.0),
            "focused_query_matches": item.get("focused_query_matches", 0),
            "rerank_score": item.get("rerank_score", item["score"]),
            "term_coverage": item.get("term_coverage", 0.0),
            "reranker_version": item.get("reranker_version", RERANKER_VERSION),
            "knowledge_points": item.get("knowledge_points", []),
            "snippet": item["chunk_text"][:500],
        }
        for item in results
    ]
    trace = {
        "trace_id": str(uuid4()),
        "retriever_version": RETRIEVER_VERSION,
        "reranker_version": RERANKER_VERSION,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "candidate_chunks": len(chunks),
        "vector_candidates": len(vector_hits),
        "keyword_candidates": len(keyword_ids),
        "candidate_knowledge_points": len(points),
        "top_k": top_k,
        "query_variants": query_variants,
        "timings_ms": {
            "load": round(load_ms, 3),
            "ranking": round(ranking_ms, 3),
            "total": round((perf_counter() - total_started) * 1000, 3),
        },
        "hits": [
            {
                "rank": rank,
                "chunk_id": item["chunk_id"],
                "kb_ids": item.get("kb_ids", []),
                "score": item["score"],
                "dense_score": item["dense_score"],
                "keyword_score": item["keyword_score"],
                "knowledge_score": item["knowledge_score"],
                "dense_rank": item.get("dense_rank"),
                "keyword_rank": item.get("keyword_rank"),
                "selection_score": item.get("selection_score", item["score"]),
                "evidence_overlap": item.get("evidence_overlap", 0),
                "coverage_penalty": item.get("coverage_penalty", 0.0),
                "focused_query_matches": item.get("focused_query_matches", 0),
            }
            for rank, item in enumerate(citations, start=1)
        ],
    }
    result = {
        "course_id": course_id,
        "course_name": course["name"],
        "query": query,
        "total": len(citations),
        "citations": citations,
        "trace": trace,
    }
    record_audit(
        user_id,
        "COURSE_VECTOR_SEARCHED",
        "course",
        course_id,
        {"query": query[:200], "result_count": len(citations), "trace": trace},
    )
    return result


def backfill_knowledge_point_vectors(
    user_id: int | None = None,
    course_id: int | None = None,
    embedding_provider: Callable = embed_texts,
) -> int:
    clauses = []
    params = []
    if user_id is not None:
        clauses.append("user_id = %s")
        params.append(user_id)
    if course_id is not None:
        clauses.append("course_id = %s")
        params.append(course_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with get_cursor() as cursor:
        cursor.execute(
            f"""
            SELECT id, user_id, course_id, name, description, summary, examples_json,
                   embedding_json, embedding_hash
            FROM knowledge_points
            {where}
            ORDER BY id
            """,
            params,
        )
        points = list(cursor.fetchall())

    pending = []
    for point in points:
        point["examples"] = json.loads(point.pop("examples_json") or "[]")
        text = _knowledge_vector_text(point)
        digest = hashlib.sha256(
            f"{EMBEDDING_MODEL_NAME}\0knowledge-v1\0{text}".encode("utf-8")
        ).hexdigest()
        if point.get("embedding_json") and point.get("embedding_hash") == digest:
            continue
        pending.append((point, text, digest))
    if not pending:
        return 0

    embeddings = embedding_provider([text for _, text, _ in pending])
    if len(embeddings) != len(pending):
        raise ValueError("知识点向量回填数量不一致")
    with get_cursor() as cursor:
        for (point, _, digest), embedding in zip(pending, embeddings):
            cursor.execute(
                """
                UPDATE knowledge_points
                SET embedding_json = %s, embedding_model = %s,
                    embedding_hash = %s, updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s AND course_id = %s
                """,
                (
                    serialize_embedding(embedding),
                    EMBEDDING_MODEL_NAME,
                    digest,
                    point["id"],
                    point["user_id"],
                    point["course_id"],
                ),
            )
    return len(pending)
