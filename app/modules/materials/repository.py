import json
from typing import Any

MATERIAL_COLUMNS = """
    id, user_id, course_id, course_name, title, content, filename,
    file_hash, parse_status, index_status, processing_status,
    processing_error, storage_path, mime_type, file_size, chunker_version,
    created_at, updated_at
"""

MATERIAL_SUMMARY_COLUMNS = """
    id, user_id, course_id, course_name, title, filename,
    file_hash, parse_status, index_status, processing_status,
    processing_error, mime_type, file_size, chunker_version, created_at, updated_at
"""


def create_text_material(cursor, user_id: int, course: dict, title: str, content: str) -> dict:
    cursor.execute(
        """
        INSERT INTO course_materials
            (user_id, course_id, course_name, title, content,
             parse_status, index_status, processing_status)
        VALUES (%s, %s, %s, %s, %s, 'parsed', 'pending', 'uploaded')
        """,
        (user_id, course["id"], course["name"], title, content),
    )
    material = get_material(cursor, cursor.lastrowid, user_id)
    if material is None:
        raise RuntimeError("material insert succeeded but the row could not be reloaded")
    return material


def create_file_material(cursor, user_id: int, course: dict, title: str, upload) -> dict:
    cursor.execute(
        """
        INSERT INTO course_materials
            (user_id, course_id, course_name, title, content, filename,
             parse_status, index_status, processing_status,
             storage_path, mime_type, file_size)
        VALUES (%s, %s, %s, %s, '', %s, 'uploaded', 'pending', 'uploaded', %s, %s, %s)
        """,
        (
            user_id,
            course["id"],
            course["name"],
            title,
            upload.original_filename,
            upload.storage_path,
            upload.mime_type,
            upload.size,
        ),
    )
    material = get_material(cursor, cursor.lastrowid, user_id)
    if material is None:
        raise RuntimeError("material insert succeeded but the row could not be reloaded")
    return material


def get_material(cursor, material_id: int, user_id: int) -> dict | None:
    cursor.execute(
        f"SELECT {MATERIAL_COLUMNS} FROM course_materials WHERE id = %s AND user_id = %s",
        (material_id, user_id),
    )
    return cursor.fetchone()


def list_course_materials(cursor, course_id: int, user_id: int) -> list[dict]:
    cursor.execute(
        f"""
        SELECT {MATERIAL_SUMMARY_COLUMNS}
        FROM course_materials
        WHERE course_id = %s AND user_id = %s
        ORDER BY id DESC
        """,
        (course_id, user_id),
    )
    return list(cursor.fetchall())


def delete_material(cursor, material_id: int, user_id: int) -> dict | None:
    """Delete one owned material while retaining mastery-bearing knowledge nodes."""
    material = get_material(cursor, material_id, user_id)
    if material is None:
        return None

    cursor.execute(
        "SELECT id FROM course_material_chunks WHERE material_id = %s AND user_id = %s",
        (material_id, user_id),
    )
    removed_chunk_ids = {int(row["id"]) for row in cursor.fetchall()}

    affected_point_ids: set[int] = set()
    if removed_chunk_ids:
        placeholders = ",".join(["%s"] * len(removed_chunk_ids))
        cursor.execute(
            f"""
            SELECT DISTINCT knowledge_point_id
            FROM knowledge_point_sources
            WHERE user_id = %s AND chunk_id IN ({placeholders})
            """,
            (user_id, *sorted(removed_chunk_ids)),
        )
        affected_point_ids = {int(row["knowledge_point_id"]) for row in cursor.fetchall()}

    cursor.execute(
        "DELETE FROM course_materials WHERE id = %s AND user_id = %s",
        (material_id, user_id),
    )

    orphaned_point_ids: list[int] = []
    for point_id in sorted(affected_point_ids):
        cursor.execute(
            """
            SELECT chunk_id FROM knowledge_point_sources
            WHERE knowledge_point_id = %s AND user_id = %s
            ORDER BY chunk_id
            """,
            (point_id, user_id),
        )
        remaining_ids = [int(row["chunk_id"]) for row in cursor.fetchall()]
        cursor.execute(
            """
            UPDATE knowledge_points
            SET source_chunk_ids = %s,
                status = %s,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s
            """,
            (
                json.dumps(remaining_ids),
                "active" if remaining_ids else "orphaned",
                point_id,
                user_id,
            ),
        )
        if not remaining_ids:
            orphaned_point_ids.append(point_id)

    return {
        "material": material,
        "removed_chunk_count": len(removed_chunk_ids),
        "removed_knowledge_point_ids": [],
        "orphaned_knowledge_point_ids": orphaned_point_ids,
    }


def update_material(cursor, material_id: int, user_id: int, **changes) -> dict | None:
    allowed = {
        "content",
        "parse_status",
        "index_status",
        "processing_status",
        "processing_error",
        "file_hash",
        "chunker_version",
    }
    updates = []
    values: list[Any] = []
    for field, value in changes.items():
        if field in allowed:
            updates.append(f"{field} = %s")
            values.append(value)
    if updates:
        values.extend([material_id, user_id])
        cursor.execute(
            f"UPDATE course_materials SET {', '.join(updates)} WHERE id = %s AND user_id = %s",
            values,
        )
    return get_material(cursor, material_id, user_id)


def replace_chunks(cursor, material: dict, chunks: list[dict]) -> list[dict]:
    cursor.execute(
        """
        SELECT id, chunk_index, content_hash, embedding_json, embedding_model,
               embedding_hash
        FROM course_material_chunks
        WHERE material_id = %s AND user_id = %s
        ORDER BY id
        """,
        (material["id"], material["user_id"]),
    )
    existing = list(cursor.fetchall())
    available_by_hash: dict[str, list[dict]] = {}
    for row in existing:
        available_by_hash.setdefault(row.get("content_hash") or "", []).append(row)
    retained_ids = set()
    stored = []
    for chunk in chunks:
        matches = available_by_hash.get(chunk.get("content_hash") or "", [])
        matched = matches.pop(0) if matches else None
        if matched:
            cursor.execute(
                """
                UPDATE course_material_chunks
                SET course_name = %s, chunk_index = %s, chunk_text = %s,
                    page_number = %s, heading_path = %s, kb_ids_json = %s,
                    document_type = %s, char_start = %s, char_end = %s,
                    chunker_version = %s, estimated_tokens = %s,
                    embedding_json = %s, embedding_model = %s,
                    embedding_hash = %s, content_hash = %s, indexed_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
                """,
                (
                    material["course_name"],
                    chunk["chunk_index"],
                    chunk["chunk_text"],
                    chunk.get("page_number"),
                    chunk.get("heading_path"),
                    json.dumps(chunk.get("kb_ids", []), ensure_ascii=False),
                    chunk.get("document_type", "content"),
                    chunk.get("char_start"),
                    chunk.get("char_end"),
                    chunk.get("chunker_version"),
                    chunk.get("estimated_tokens"),
                    chunk["embedding_json"],
                    chunk["embedding_model"],
                    chunk.get("embedding_hash"),
                    chunk["content_hash"],
                    matched["id"],
                    material["user_id"],
                ),
            )
            chunk_id = matched["id"]
        else:
            cursor.execute(
                """
                INSERT INTO course_material_chunks
                    (user_id, material_id, course_name, chunk_index, chunk_text,
                     page_number, heading_path, kb_ids_json, document_type,
                     char_start, char_end, chunker_version, estimated_tokens,
                     embedding_json, embedding_model, embedding_hash, content_hash, indexed_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """,
                (
                    material["user_id"],
                    material["id"],
                    material["course_name"],
                    chunk["chunk_index"],
                    chunk["chunk_text"],
                    chunk.get("page_number"),
                    chunk.get("heading_path"),
                    json.dumps(chunk.get("kb_ids", []), ensure_ascii=False),
                    chunk.get("document_type", "content"),
                    chunk.get("char_start"),
                    chunk.get("char_end"),
                    chunk.get("chunker_version"),
                    chunk.get("estimated_tokens"),
                    chunk["embedding_json"],
                    chunk["embedding_model"],
                    chunk.get("embedding_hash"),
                    chunk["content_hash"],
                ),
            )
            chunk_id = cursor.lastrowid
        retained_ids.add(chunk_id)
        stored.append({**chunk, "id": chunk_id})

    stale_ids = [row["id"] for row in existing if row["id"] not in retained_ids]
    if stale_ids:
        placeholders = ",".join(["%s"] * len(stale_ids))
        cursor.execute(
            f"DELETE FROM course_material_chunks WHERE user_id = %s AND id IN ({placeholders})",
            (material["user_id"], *stale_ids),
        )
    return stored


def upsert_knowledge_points(cursor, user_id: int, course_id: int, points: list[dict]) -> list[dict]:
    stored = []
    for order, point in enumerate(points):
        cursor.execute(
            """
            SELECT source_chunk_ids FROM knowledge_points
            WHERE user_id = %s AND course_id = %s AND name = %s
            """,
            (user_id, course_id, point["name"]),
        )
        existing = cursor.fetchone()
        source_chunk_ids = set(point.get("source_chunk_ids", []))
        if existing:
            source_chunk_ids.update(json.loads(existing.get("source_chunk_ids") or "[]"))
        if source_chunk_ids:
            placeholders = ",".join(["%s"] * len(source_chunk_ids))
            cursor.execute(
                f"""
                SELECT chunk.id
                FROM course_material_chunks chunk
                JOIN course_materials material ON material.id = chunk.material_id
                WHERE chunk.user_id = %s AND material.course_id = %s
                  AND chunk.id IN ({placeholders})
                """,
                (user_id, course_id, *sorted(source_chunk_ids)),
            )
            source_chunk_ids = {row["id"] for row in cursor.fetchall()}
        cursor.execute(
            """
            INSERT INTO knowledge_points
                (user_id, course_id, name, description, summary, examples_json,
                 source_chunk_ids, sort_order, embedding_json, embedding_model, embedding_hash,
                 knowledge_level, category, extraction_confidence, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'active')
            ON DUPLICATE KEY UPDATE
                description = VALUES(description),
                summary = VALUES(summary),
                examples_json = VALUES(examples_json),
                source_chunk_ids = VALUES(source_chunk_ids),
                sort_order = LEAST(sort_order, VALUES(sort_order)),
                embedding_json = VALUES(embedding_json),
                embedding_model = VALUES(embedding_model),
                embedding_hash = VALUES(embedding_hash),
                knowledge_level = VALUES(knowledge_level),
                category = VALUES(category),
                extraction_confidence = VALUES(extraction_confidence),
                status = 'active',
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                course_id,
                point["name"],
                point.get("description", ""),
                point.get("summary", ""),
                json.dumps(point.get("examples", []), ensure_ascii=False),
                json.dumps(sorted(source_chunk_ids), ensure_ascii=False),
                order,
                point.get("embedding_json"),
                point.get("embedding_model"),
                point.get("embedding_hash"),
                point.get("knowledge_level", "concept"),
                point.get("category"),
                float(point.get("confidence", 0.8)),
            ),
        )
        cursor.execute(
            """
            SELECT id, course_id, name, description, summary, examples_json,
                   source_chunk_ids, sort_order,
                   embedding_json, embedding_model, embedding_hash, created_at, updated_at
            FROM knowledge_points
            WHERE user_id = %s AND course_id = %s AND name = %s
            """,
            (user_id, course_id, point["name"]),
        )
        row = cursor.fetchone()
        row["examples"] = json.loads(row.pop("examples_json") or "[]")
        row["source_chunk_ids"] = json.loads(row.get("source_chunk_ids") or "[]")
        for chunk_id in row["source_chunk_ids"]:
            cursor.execute(
                """
                INSERT INTO knowledge_point_sources
                    (knowledge_point_id, chunk_id, material_id, user_id, course_id,
                     evidence_type, confidence)
                SELECT %s, chunk.id, chunk.material_id, %s, %s, 'extracted', %s
                FROM course_material_chunks chunk
                JOIN course_materials material ON material.id = chunk.material_id
                WHERE chunk.id = %s AND chunk.user_id = %s
                  AND material.course_id = %s AND material.user_id = %s
                ON DUPLICATE KEY UPDATE
                    confidence = GREATEST(confidence, VALUES(confidence))
                """,
                (
                    row["id"], user_id, course_id,
                    float(point.get("confidence", 0.8)),
                    chunk_id, user_id, course_id, user_id,
                ),
            )
        stored.append(row)
    by_name = {point["name"]: point for point in stored}
    for source, payload in zip(stored, points):
        parent_name = str(payload.get("parent_name") or "").strip()
        parent = by_name.get(parent_name)
        if not parent or parent["id"] == source["id"]:
            continue
        cursor.execute(
            """
            UPDATE knowledge_points SET parent_point_id = %s
            WHERE id = %s AND user_id = %s AND course_id = %s
            """,
            (parent["id"], source["id"], user_id, course_id),
        )
    return stored


def list_knowledge_points(cursor, course_id: int, user_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT id, course_id, name, description, summary, examples_json,
               source_chunk_ids, sort_order,
               embedding_json, embedding_model, embedding_hash,
               knowledge_level, parent_point_id, category, extraction_confidence,
               status, created_at, updated_at
        FROM knowledge_points
        WHERE course_id = %s AND user_id = %s AND status = 'active'
        ORDER BY sort_order, id
        """,
        (course_id, user_id),
    )
    points = []
    for row in cursor.fetchall():
        row["examples"] = json.loads(row.pop("examples_json") or "[]")
        row["source_chunk_ids"] = json.loads(row.get("source_chunk_ids") or "[]")
        points.append(row)
    return points


def replace_material_search_terms(
    cursor,
    user_id: int,
    course_id: int,
    material_id: int,
    documents: list[dict],
) -> None:
    cursor.execute(
        "DELETE FROM course_material_search_terms WHERE material_id = %s AND user_id = %s",
        (material_id, user_id),
    )
    rows = []
    for document in documents:
        frequencies = document.get("term_frequencies") or {}
        length = int(document.get("document_length") or sum(frequencies.values()))
        for term, frequency in frequencies.items():
            rows.append(
                (
                    user_id, course_id, material_id, int(document["id"]),
                    str(term)[:100], min(65535, int(frequency)), max(0, length),
                )
            )
    if rows:
        cursor.executemany(
            """
            INSERT INTO course_material_search_terms
                (user_id, course_id, material_id, chunk_id, term,
                 term_frequency, document_length)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                term_frequency = VALUES(term_frequency),
                document_length = VALUES(document_length)
            """,
            rows,
        )


def count_course_search_terms(cursor, user_id: int, course_id: int) -> int:
    cursor.execute(
        """
        SELECT COUNT(*) AS total FROM course_material_search_terms
        WHERE user_id = %s AND course_id = %s
        """,
        (user_id, course_id),
    )
    return int(cursor.fetchone()["total"])


def keyword_candidate_ids(
    cursor,
    user_id: int,
    course_id: int,
    terms: list[str],
    limit: int,
) -> list[int]:
    unique_terms = list(dict.fromkeys(term[:100] for term in terms if term))[:80]
    if not unique_terms:
        return []
    placeholders = ",".join(["%s"] * len(unique_terms))
    cursor.execute(
        f"""
        SELECT chunk_id, COUNT(DISTINCT term) AS matched_terms,
               SUM(term_frequency) AS matched_frequency
        FROM course_material_search_terms
        WHERE user_id = %s AND course_id = %s AND term IN ({placeholders})
        GROUP BY chunk_id
        ORDER BY matched_terms DESC, matched_frequency DESC, chunk_id
        LIMIT %s
        """,
        (user_id, course_id, *unique_terms, int(limit)),
    )
    return [int(row["chunk_id"]) for row in cursor.fetchall()]


def list_course_vector_rows(cursor, course_id: int, user_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT chunk.id, chunk.embedding_json
        FROM course_material_chunks chunk
        JOIN course_materials material ON material.id = chunk.material_id
        WHERE material.course_id = %s AND material.user_id = %s
          AND chunk.user_id = %s AND material.processing_status = 'ready'
          AND chunk.embedding_json IS NOT NULL
          AND COALESCE(chunk.document_type, 'content') <> 'index'
        ORDER BY chunk.id
        """,
        (course_id, user_id, user_id),
    )
    return list(cursor.fetchall())


def get_course_search_rows(cursor, course_id: int, user_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT chunk.id, chunk.material_id, chunk.chunk_text, chunk.heading_path,
               chunk.kb_ids_json, material.title AS material_title
        FROM course_material_chunks chunk
        JOIN course_materials material ON material.id = chunk.material_id
        WHERE material.course_id = %s AND material.user_id = %s
          AND chunk.user_id = %s AND material.processing_status = 'ready'
          AND COALESCE(chunk.document_type, 'content') <> 'index'
        ORDER BY chunk.id
        """,
        (course_id, user_id, user_id),
    )
    rows = list(cursor.fetchall())
    for row in rows:
        row["kb_ids"] = json.loads(row.pop("kb_ids_json") or "[]")
    return rows


def get_course_chunks_by_ids(
    cursor,
    course_id: int,
    user_id: int,
    chunk_ids: list[int],
) -> list[dict]:
    ids = list(dict.fromkeys(int(value) for value in chunk_ids if int(value) > 0))
    if not ids:
        return []
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(
        f"""
        SELECT chunks.id, chunks.material_id, chunks.chunk_index, chunks.chunk_text,
               chunks.page_number, chunks.heading_path, chunks.kb_ids_json,
               chunks.document_type, chunks.char_start, chunks.char_end,
               chunks.chunker_version, chunks.estimated_tokens,
               chunks.embedding_json, chunks.embedding_model, chunks.embedding_hash,
               chunks.content_hash, chunks.indexed_at,
               materials.title AS material_title, materials.filename
        FROM course_material_chunks chunks
        JOIN course_materials materials ON materials.id = chunks.material_id
        WHERE materials.course_id = %s AND materials.user_id = %s
          AND chunks.user_id = %s AND chunks.id IN ({placeholders})
          AND materials.processing_status = 'ready'
          AND COALESCE(chunks.document_type, 'content') <> 'index'
        """,
        (course_id, user_id, user_id, *ids),
    )
    by_id = {}
    for row in cursor.fetchall():
        row["kb_ids"] = json.loads(row.pop("kb_ids_json") or "[]")
        by_id[int(row["id"])] = row
    return [by_id[value] for value in ids if value in by_id]


def get_course_neighbor_chunks(
    cursor,
    course_id: int,
    user_id: int,
    anchor_ids: list[int],
    window: int,
) -> list[dict]:
    anchors = get_course_chunks_by_ids(cursor, course_id, user_id, anchor_ids)
    if not anchors:
        return []
    clauses = []
    params: list[Any] = [course_id, user_id, user_id]
    for anchor in anchors:
        clauses.append("(chunks.material_id = %s AND chunks.chunk_index BETWEEN %s AND %s)")
        index = int(anchor["chunk_index"])
        params.extend([int(anchor["material_id"]), index - window, index + window])
    cursor.execute(
        f"""
        SELECT chunks.id, chunks.material_id, chunks.chunk_index, chunks.chunk_text,
               chunks.page_number, chunks.heading_path, chunks.kb_ids_json,
               chunks.document_type, chunks.char_start, chunks.char_end,
               chunks.chunker_version, chunks.estimated_tokens,
               chunks.embedding_json, chunks.embedding_model, chunks.embedding_hash,
               chunks.content_hash, chunks.indexed_at,
               materials.title AS material_title, materials.filename
        FROM course_material_chunks chunks
        JOIN course_materials materials ON materials.id = chunks.material_id
        WHERE materials.course_id = %s AND materials.user_id = %s
          AND chunks.user_id = %s AND ({' OR '.join(clauses)})
          AND materials.processing_status = 'ready'
          AND COALESCE(chunks.document_type, 'content') <> 'index'
        ORDER BY chunks.material_id, chunks.chunk_index, chunks.id
        """,
        params,
    )
    rows = list(cursor.fetchall())
    for row in rows:
        row["kb_ids"] = json.loads(row.pop("kb_ids_json") or "[]")
    return rows


def list_course_outline_rows(
    cursor,
    course_id: int,
    user_id: int,
    material_id: int | None = None,
) -> list[dict]:
    material_clause = "AND materials.id = %s" if material_id is not None else ""
    params: list[Any] = [course_id, user_id, user_id]
    if material_id is not None:
        params.append(int(material_id))
    cursor.execute(
        f"""
        SELECT materials.id AS material_id, materials.title AS material_title,
               materials.filename, COALESCE(chunks.heading_path, '') AS heading_path,
               COUNT(*) AS chunk_count,
               COALESCE(SUM(chunks.estimated_tokens), 0) AS estimated_tokens,
               MIN(chunks.id) AS first_chunk_id,
               MIN(chunks.page_number) AS page_start,
               MAX(chunks.page_number) AS page_end
        FROM course_material_chunks chunks
        JOIN course_materials materials ON materials.id = chunks.material_id
        WHERE materials.course_id = %s AND materials.user_id = %s
          AND chunks.user_id = %s AND materials.processing_status = 'ready'
          AND COALESCE(chunks.document_type, 'content') <> 'index'
          {material_clause}
        GROUP BY materials.id, materials.title, materials.filename,
                 COALESCE(chunks.heading_path, '')
        ORDER BY materials.id, first_chunk_id
        """,
        params,
    )
    return list(cursor.fetchall())


def get_course_section_chunks(
    cursor,
    course_id: int,
    user_id: int,
    material_id: int,
    heading_path: str,
) -> list[dict]:
    normalized = (heading_path or "").strip()
    for operator, value in (("=", normalized), ("LIKE", f"%{normalized}%")):
        cursor.execute(
            f"""
            SELECT chunks.id, chunks.material_id, chunks.chunk_index, chunks.chunk_text,
                   chunks.page_number, chunks.heading_path, chunks.kb_ids_json,
                   chunks.document_type, chunks.char_start, chunks.char_end,
                   chunks.chunker_version, chunks.estimated_tokens,
                   materials.title AS material_title, materials.filename
            FROM course_material_chunks chunks
            JOIN course_materials materials ON materials.id = chunks.material_id
            WHERE materials.course_id = %s AND materials.user_id = %s
              AND materials.id = %s AND chunks.user_id = %s
              AND COALESCE(chunks.heading_path, '') {operator} %s
              AND materials.processing_status = 'ready'
              AND COALESCE(chunks.document_type, 'content') <> 'index'
            ORDER BY chunks.chunk_index, chunks.id
            LIMIT 1000
            """,
            (course_id, user_id, material_id, user_id, value),
        )
        rows = list(cursor.fetchall())
        if rows:
            for row in rows:
                row["kb_ids"] = json.loads(row.pop("kb_ids_json") or "[]")
            return rows
    return []


def list_knowledge_points_for_chunks(
    cursor,
    course_id: int,
    user_id: int,
    chunk_ids: list[int],
) -> list[dict]:
    ids = list(dict.fromkeys(int(value) for value in chunk_ids if int(value) > 0))
    if not ids:
        return []
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(
        f"""
        SELECT DISTINCT point.id, point.course_id, point.name, point.description,
               point.summary, point.examples_json, point.source_chunk_ids,
               point.sort_order, point.embedding_json, point.embedding_model,
               point.embedding_hash, point.knowledge_level, point.parent_point_id,
               point.category, point.extraction_confidence, point.status,
               point.created_at, point.updated_at
        FROM knowledge_points point
        JOIN knowledge_point_sources source ON source.knowledge_point_id = point.id
        WHERE point.course_id = %s AND point.user_id = %s AND point.status = 'active'
          AND source.chunk_id IN ({placeholders})
        ORDER BY point.sort_order, point.id
        """,
        (course_id, user_id, *ids),
    )
    points = []
    for row in cursor.fetchall():
        row["examples"] = json.loads(row.pop("examples_json") or "[]")
        row["source_chunk_ids"] = json.loads(row.get("source_chunk_ids") or "[]")
        points.append(row)
    return points


def list_knowledge_point_relations(cursor, course_id: int, user_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT relation.id, relation.source_point_id, relation.target_point_id,
               relation.relation_type, relation.confidence,
               relation.evidence_chunk_id, relation.rationale,
               source.name AS source_name, target.name AS target_name
        FROM knowledge_point_relations relation
        JOIN knowledge_points source ON source.id = relation.source_point_id
        JOIN knowledge_points target ON target.id = relation.target_point_id
        WHERE relation.course_id = %s AND relation.user_id = %s
        ORDER BY source.sort_order, target.sort_order, relation.id
        """,
        (course_id, user_id),
    )
    return list(cursor.fetchall())


def add_sequential_knowledge_relations(
    cursor,
    user_id: int,
    course_id: int,
    point_ids: list[int],
) -> None:
    for source_id, target_id in zip(point_ids, point_ids[1:]):
        if source_id == target_id:
            continue
        cursor.execute(
            """
            INSERT INTO knowledge_point_relations
                (user_id, course_id, source_point_id, target_point_id,
                 relation_type, confidence)
            VALUES (%s, %s, %s, %s, 'prerequisite', 0.5500)
            ON DUPLICATE KEY UPDATE confidence = GREATEST(confidence, VALUES(confidence))
            """,
            (user_id, course_id, source_id, target_id),
        )


def upsert_evidence_backed_relations(
    cursor,
    user_id: int,
    course_id: int,
    points: list[dict],
    relations: list[dict],
) -> None:
    by_name = {str(point["name"]).strip(): point for point in points}
    for relation in relations:
        source = by_name.get(str(relation.get("source_name") or "").strip())
        target = by_name.get(str(relation.get("target_name") or "").strip())
        if not source or not target or source["id"] == target["id"]:
            continue
        relation_type = str(relation.get("relation_type") or "related").strip().lower()
        if relation_type not in {"prerequisite", "part_of", "related", "contrasts", "applies_to"}:
            relation_type = "related"
        evidence_chunk_id = relation.get("evidence_chunk_id")
        if evidence_chunk_id is not None:
            cursor.execute(
                """
                SELECT 1 FROM course_material_chunks chunk
                JOIN course_materials material ON material.id = chunk.material_id
                WHERE chunk.id = %s AND chunk.user_id = %s
                  AND material.course_id = %s AND material.user_id = %s
                """,
                (int(evidence_chunk_id), user_id, course_id, user_id),
            )
            if cursor.fetchone() is None:
                evidence_chunk_id = None
        cursor.execute(
            """
            INSERT INTO knowledge_point_relations
                (user_id, course_id, source_point_id, target_point_id,
                 relation_type, confidence, evidence_chunk_id, rationale)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                confidence = GREATEST(confidence, VALUES(confidence)),
                evidence_chunk_id = COALESCE(VALUES(evidence_chunk_id), evidence_chunk_id),
                rationale = COALESCE(VALUES(rationale), rationale)
            """,
            (
                user_id, course_id, source["id"], target["id"], relation_type,
                float(relation.get("confidence", 0.7)), evidence_chunk_id,
                str(relation.get("rationale") or "")[:500] or None,
            ),
        )


def get_material_chunks(cursor, material_id: int, user_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT id, chunk_index, chunk_text, page_number, heading_path, kb_ids_json,
               document_type, char_start, char_end, chunker_version, estimated_tokens,
               embedding_json, embedding_model, embedding_hash, content_hash, indexed_at
        FROM course_material_chunks
        WHERE material_id = %s AND user_id = %s
        ORDER BY chunk_index, id
        """,
        (material_id, user_id),
    )
    chunks = list(cursor.fetchall())
    for chunk in chunks:
        chunk["kb_ids"] = json.loads(chunk.pop("kb_ids_json") or "[]")
    return chunks


def get_course_chunk(cursor, course_id: int, chunk_id: int, user_id: int) -> dict | None:
    cursor.execute(
        """
        SELECT chunks.id, chunks.material_id, chunks.chunk_index, chunks.chunk_text,
               chunks.page_number, chunks.heading_path, chunks.char_start, chunks.char_end,
               materials.title AS material_title, materials.filename
        FROM course_material_chunks chunks
        JOIN course_materials materials ON materials.id = chunks.material_id
        WHERE chunks.id = %s AND chunks.user_id = %s AND materials.course_id = %s
        """,
        (chunk_id, user_id, course_id),
    )
    return cursor.fetchone()


def get_course_chunks(cursor, course_id: int, user_id: int) -> list[dict]:
    cursor.execute(
        """
        SELECT chunks.id, chunks.material_id, chunks.chunk_index, chunks.chunk_text,
               chunks.page_number, chunks.heading_path, chunks.kb_ids_json,
               chunks.document_type, chunks.char_start, chunks.char_end,
               chunks.chunker_version, chunks.estimated_tokens,
               chunks.embedding_json, chunks.embedding_model, chunks.embedding_hash,
               chunks.content_hash, chunks.indexed_at,
               materials.title AS material_title, materials.filename
        FROM course_material_chunks chunks
        JOIN course_materials materials ON materials.id = chunks.material_id
        WHERE materials.course_id = %s
          AND chunks.user_id = %s
          AND materials.user_id = %s
          AND materials.processing_status = 'ready'
          AND chunks.embedding_json IS NOT NULL
          AND COALESCE(chunks.document_type, 'content') <> 'index'
        ORDER BY chunks.id
        """,
        (course_id, user_id, user_id),
    )
    chunks = list(cursor.fetchall())
    for chunk in chunks:
        chunk["kb_ids"] = json.loads(chunk.pop("kb_ids_json") or "[]")
    return chunks


def set_course_status(cursor, course_id: int, user_id: int, status: str) -> None:
    cursor.execute(
        "UPDATE courses SET status = %s WHERE id = %s AND user_id = %s",
        (status, course_id, user_id),
    )
