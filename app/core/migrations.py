import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from app.core.database import get_conn

ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATION_SQL_DIR = ROOT_DIR / "sql" / "migrations"
IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


@dataclass(frozen=True)
class Migration:
    version: str
    name: str
    upgrade: Callable


def _identifier(value: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"非法 SQL 标识符：{value}")
    return value


def _table_exists(cursor, table: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.tables
        WHERE table_schema = DATABASE() AND table_name = %s
        """,
        (_identifier(table),),
    )
    return cursor.fetchone()["total"] > 0


def _column_exists(cursor, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND column_name = %s
        """,
        (_identifier(table), _identifier(column)),
    )
    return cursor.fetchone()["total"] > 0


def _index_exists(cursor, table: str, index_name: str) -> bool:
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND index_name = %s
        """,
        (_identifier(table), _identifier(index_name)),
    )
    return cursor.fetchone()["total"] > 0


def _add_column(cursor, table: str, column: str, definition: str) -> None:
    if not _table_exists(cursor, table) or _column_exists(cursor, table, column):
        return
    cursor.execute(
        f"ALTER TABLE `{_identifier(table)}` ADD COLUMN `{_identifier(column)}` {definition}"
    )


def _modify_column(cursor, table: str, column: str, definition: str) -> None:
    if not _table_exists(cursor, table) or not _column_exists(cursor, table, column):
        return
    cursor.execute(
        f"ALTER TABLE `{_identifier(table)}` MODIFY COLUMN `{_identifier(column)}` {definition}"
    )


def _add_index(cursor, table: str, index_name: str, columns: str) -> None:
    if not _table_exists(cursor, table) or _index_exists(cursor, table, index_name):
        return
    cursor.execute(
        f"CREATE INDEX `{_identifier(index_name)}` ON `{_identifier(table)}` ({columns})"
    )


def _add_unique_index(cursor, table: str, index_name: str, columns: str) -> None:
    if not _table_exists(cursor, table) or _index_exists(cursor, table, index_name):
        return
    cursor.execute(
        f"CREATE UNIQUE INDEX `{_identifier(index_name)}` ON `{_identifier(table)}` ({columns})"
    )


def _drop_index(cursor, table: str, index_name: str) -> None:
    if not _table_exists(cursor, table) or not _index_exists(cursor, table, index_name):
        return
    cursor.execute(f"DROP INDEX `{_identifier(index_name)}` ON `{_identifier(table)}`")


def _split_sql(script: str) -> list[str]:
    statements = []
    buffer = []
    for raw_line in script.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("--"):
            continue
        buffer.append(raw_line)
        if line.endswith(";"):
            statement = "\n".join(buffer).strip().rstrip(";").strip()
            if statement:
                statements.append(statement)
            buffer = []
    if buffer:
        statements.append("\n".join(buffer).strip())
    return statements


def _upgrade_baseline(cursor) -> None:
    script = (MIGRATION_SQL_DIR / "0001_baseline.sql").read_text(encoding="utf-8")
    for statement in _split_sql(script):
        cursor.execute(statement)


def _upgrade_course_learning_foundation(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS courses (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            name VARCHAR(100) NOT NULL,
            goal VARCHAR(500) NOT NULL DEFAULT '',
            exam_at DATETIME NULL,
            daily_minutes INT NOT NULL DEFAULT 30,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            is_current BOOLEAN NOT NULL DEFAULT FALSE,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_courses_user_status (user_id, status),
            INDEX idx_courses_user_current (user_id, is_current),
            CONSTRAINT fk_courses_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    for table in ["course_materials", "learning_resources", "quiz_sets", "tasks"]:
        _add_column(cursor, table, "course_id", "INT NULL")
        _add_index(cursor, table, f"idx_{table}_course_id", "course_id")

    _add_column(cursor, "course_materials", "filename", "VARCHAR(255) NULL")
    _add_column(cursor, "course_materials", "file_hash", "VARCHAR(64) NULL")
    _add_column(cursor, "course_materials", "parse_status", "VARCHAR(30) NOT NULL DEFAULT 'uploaded'")
    _add_column(cursor, "course_materials", "index_status", "VARCHAR(30) NOT NULL DEFAULT 'pending'")
    _add_column(cursor, "course_materials", "processing_error", "TEXT NULL")
    _add_column(
        cursor,
        "course_materials",
        "updated_at",
        "DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP",
    )

    _add_column(cursor, "course_material_chunks", "page_number", "INT NULL")
    _add_column(cursor, "course_material_chunks", "embedding_json", "LONGTEXT NULL")
    _add_column(cursor, "course_material_chunks", "embedding_model", "VARCHAR(120) NULL")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_points (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            name VARCHAR(150) NOT NULL,
            description TEXT NULL,
            source_chunk_ids JSON NULL,
            sort_order INT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_knowledge_point_name (user_id, course_id, name),
            INDEX idx_knowledge_points_course (course_id, sort_order),
            CONSTRAINT fk_knowledge_points_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_knowledge_points_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )

    _add_column(cursor, "quiz_questions", "knowledge_point_id", "INT NULL")
    _add_column(cursor, "learning_evaluations", "course_id", "INT NULL")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mastery_records (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            knowledge_point_id INT NOT NULL,
            mastery DECIMAL(5,2) NOT NULL DEFAULT 0,
            last_evaluation_id INT NULL,
            low_score_streak INT NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_mastery_user_point (user_id, course_id, knowledge_point_id),
            INDEX idx_mastery_course_value (course_id, mastery),
            CONSTRAINT fk_mastery_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_mastery_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_mastery_point FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS mastery_changes (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            mastery_record_id BIGINT NOT NULL,
            evaluation_id INT NULL,
            before_value DECIMAL(5,2) NOT NULL,
            after_value DECIMAL(5,2) NOT NULL,
            reason VARCHAR(500) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_mastery_changes_record (mastery_record_id, created_at),
            CONSTRAINT fk_mastery_changes_record FOREIGN KEY (mastery_record_id) REFERENCES mastery_records(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS study_plans (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            title VARCHAR(255) NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'draft',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_study_plans_course_status (course_id, status),
            CONSTRAINT fk_study_plans_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_study_plans_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS study_sessions (
            id INT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            plan_id INT NULL,
            scheduled_date DATE NOT NULL,
            estimated_minutes INT NOT NULL DEFAULT 30,
            actual_minutes INT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'planned',
            adaptation_reason VARCHAR(500) NULL,
            started_at DATETIME NULL,
            completed_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_study_sessions_user_date (user_id, scheduled_date, status),
            INDEX idx_study_sessions_course_date (course_id, scheduled_date),
            CONSTRAINT fk_study_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_study_sessions_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_study_sessions_plan FOREIGN KEY (plan_id) REFERENCES study_plans(id) ON DELETE SET NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS study_session_items (
            id INT AUTO_INCREMENT PRIMARY KEY,
            session_id INT NOT NULL,
            knowledge_point_id INT NULL,
            item_type VARCHAR(30) NOT NULL,
            title VARCHAR(255) NOT NULL,
            content_ref JSON NULL,
            sort_order INT NOT NULL DEFAULT 0,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_session_items_order (session_id, sort_order),
            CONSTRAINT fk_session_items_session FOREIGN KEY (session_id) REFERENCES study_sessions(id) ON DELETE CASCADE,
            CONSTRAINT fk_session_items_point FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id) ON DELETE SET NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_sessions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NULL,
            title VARCHAR(255) NOT NULL DEFAULT '新对话',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            INDEX idx_chat_sessions_user_updated (user_id, updated_at),
            CONSTRAINT fk_chat_sessions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_chat_sessions_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
        )
        """
    )

    _add_column(cursor, "agent_chat_messages", "session_id", "BIGINT NULL")
    _add_column(cursor, "agent_chat_messages", "course_id", "INT NULL")
    _add_column(cursor, "agent_chat_messages", "sources_json", "TEXT NULL")
    _add_index(cursor, "agent_chat_messages", "idx_agent_chat_session_id", "session_id, id")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluation_answers (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            evaluation_id INT NOT NULL,
            question_id INT NOT NULL,
            knowledge_point_id INT NULL,
            user_answer TEXT NOT NULL,
            score DECIMAL(5,2) NOT NULL DEFAULT 0,
            feedback TEXT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_evaluation_answers_evaluation (evaluation_id),
            INDEX idx_evaluation_answers_point (knowledge_point_id),
            CONSTRAINT fk_evaluation_answers_evaluation FOREIGN KEY (evaluation_id) REFERENCES learning_evaluations(id) ON DELETE CASCADE,
            CONSTRAINT fk_evaluation_answers_question FOREIGN KEY (question_id) REFERENCES quiz_questions(id) ON DELETE CASCADE,
            CONSTRAINT fk_evaluation_answers_point FOREIGN KEY (knowledge_point_id) REFERENCES knowledge_points(id) ON DELETE SET NULL
        )
        """
    )


def _upgrade_backfill_courses(cursor) -> None:
    cursor.execute(
        """
        INSERT INTO courses (user_id, name, status, is_current)
        SELECT source.user_id, source.course_name, 'active', FALSE
        FROM (
            SELECT user_id, course_name FROM course_materials
            WHERE course_name IS NOT NULL AND TRIM(course_name) <> ''
            UNION
            SELECT user_id, course_name FROM learning_resources
            WHERE course_name IS NOT NULL AND TRIM(course_name) <> ''
            UNION
            SELECT user_id, course_name FROM quiz_sets
            WHERE course_name IS NOT NULL AND TRIM(course_name) <> ''
        ) AS source
        WHERE NOT EXISTS (
            SELECT 1
            FROM courses existing
            WHERE existing.user_id = source.user_id
              AND existing.name = source.course_name
        )
        """
    )

    cursor.execute(
        """
        UPDATE courses selected
        JOIN (
            SELECT user_id, MIN(id) AS selected_id
            FROM courses
            WHERE status <> 'archived'
            GROUP BY user_id
        ) choice ON choice.selected_id = selected.id
        LEFT JOIN courses current_course
          ON current_course.user_id = selected.user_id
         AND current_course.is_current = TRUE
         AND current_course.status <> 'archived'
        SET selected.is_current = TRUE
        WHERE current_course.id IS NULL
        """
    )

    for table in ["course_materials", "learning_resources", "quiz_sets"]:
        cursor.execute(
            f"""
            UPDATE `{_identifier(table)}` item
            JOIN (
                SELECT user_id, name, MIN(id) AS course_id
                FROM courses
                GROUP BY user_id, name
            ) course
              ON course.user_id = item.user_id
             AND course.name = item.course_name
            SET item.course_id = course.course_id
            WHERE item.course_id IS NULL
            """
        )


def _upgrade_material_processing_metadata(cursor) -> None:
    _add_column(cursor, "course_materials", "processing_status", "VARCHAR(30) NOT NULL DEFAULT 'uploaded'")
    _add_column(cursor, "course_materials", "storage_path", "VARCHAR(500) NULL")
    _add_column(cursor, "course_materials", "mime_type", "VARCHAR(150) NULL")
    _add_column(cursor, "course_materials", "file_size", "BIGINT NULL")
    _add_index(cursor, "course_materials", "idx_materials_processing_status", "user_id, processing_status")


def _upgrade_learning_loop_metadata(cursor) -> None:
    _add_column(cursor, "quiz_sets", "purpose", "VARCHAR(30) NOT NULL DEFAULT 'practice'")
    if _table_exists(cursor, "quiz_questions"):
        cursor.execute("ALTER TABLE quiz_questions MODIFY COLUMN question VARCHAR(500) NOT NULL")
        cursor.execute("ALTER TABLE quiz_questions MODIFY COLUMN answer TEXT NOT NULL")
    _add_column(cursor, "study_session_items", "source_key", "VARCHAR(150) NULL")
    _add_index(cursor, "study_session_items", "idx_session_items_source_key", "session_id, source_key")


def _upgrade_agent_session_safety(cursor) -> None:
    _add_column(cursor, "chat_sessions", "archived_at", "DATETIME NULL")
    _add_column(cursor, "agent_chat_messages", "client_time_hint", "VARCHAR(64) NULL")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_action_requests (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            session_id BIGINT NOT NULL,
            course_id INT NULL,
            tool_name VARCHAR(80) NOT NULL,
            risk_level VARCHAR(30) NOT NULL,
            payload_json JSON NOT NULL,
            idempotency_key VARCHAR(100) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            result_json JSON NULL,
            expires_at DATETIME NOT NULL,
            confirmed_at DATETIME NULL,
            executed_at DATETIME NULL,
            server_time_utc DATETIME(6) NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_agent_action_idempotency (idempotency_key),
            INDEX idx_agent_actions_user_status (user_id, status, created_at),
            INDEX idx_agent_actions_session (session_id, created_at),
            CONSTRAINT fk_agent_actions_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_agent_actions_session FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
            CONSTRAINT fk_agent_actions_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE SET NULL
        )
        """
    )


def _upgrade_course_agent_foundation(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS course_agents (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            name VARCHAR(150) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            system_prompt TEXT NULL,
            conversation_summary TEXT NULL,
            primary_session_id BIGINT NULL,
            last_active_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_course_agents_course (course_id),
            INDEX idx_course_agents_user_status (user_id, status),
            CONSTRAINT fk_course_agents_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_course_agents_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_course_agents_primary_session FOREIGN KEY (primary_session_id)
                REFERENCES chat_sessions(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        INSERT INTO course_agents (user_id, course_id, name, status)
        SELECT user_id, id, CONCAT(name, ' 学习助手'),
               CASE WHEN status = 'archived' THEN 'archived' ELSE 'active' END
        FROM courses
        ON DUPLICATE KEY UPDATE
            name = VALUES(name),
            status = VALUES(status)
        """
    )
    cursor.execute(
        """
        INSERT INTO chat_sessions (user_id, course_id, title)
        SELECT agent.user_id, agent.course_id, CONCAT(course.name, ' 学习对话')
        FROM course_agents agent
        JOIN courses course ON course.id = agent.course_id
        WHERE NOT EXISTS (
            SELECT 1 FROM chat_sessions session
            WHERE session.user_id = agent.user_id
              AND session.course_id = agent.course_id
              AND session.archived_at IS NULL
        )
        """
    )
    cursor.execute(
        """
        UPDATE course_agents agent
        JOIN (
            SELECT session.user_id, session.course_id, MAX(session.id) AS session_id
            FROM chat_sessions session
            WHERE session.course_id IS NOT NULL AND session.archived_at IS NULL
            GROUP BY session.user_id, session.course_id
        ) selected
          ON selected.user_id = agent.user_id
         AND selected.course_id = agent.course_id
        SET agent.primary_session_id = selected.session_id
        WHERE agent.primary_session_id IS NULL
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS course_agent_memories (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            agent_id BIGINT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            memory_key VARCHAR(120) NOT NULL,
            memory_type VARCHAR(40) NOT NULL DEFAULT 'course_preference',
            content_json JSON NOT NULL,
            source_message_id INT NULL,
            source_type VARCHAR(30) NOT NULL DEFAULT 'manual',
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_course_agent_memory_key (agent_id, memory_key),
            INDEX idx_course_agent_memories_course (user_id, course_id, status),
            CONSTRAINT fk_course_agent_memories_agent FOREIGN KEY (agent_id)
                REFERENCES course_agents(id) ON DELETE CASCADE,
            CONSTRAINT fk_course_agent_memories_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_course_agent_memories_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_course_agent_memories_message FOREIGN KEY (source_message_id)
                REFERENCES agent_chat_messages(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_runs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            request_id CHAR(36) NOT NULL,
            agent_id BIGINT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            session_id BIGINT NOT NULL,
            user_message_id INT NULL,
            assistant_message_id INT NULL,
            intent VARCHAR(80) NOT NULL DEFAULT 'course_qa',
            risk_level VARCHAR(30) NOT NULL DEFAULT 'read',
            status VARCHAR(30) NOT NULL DEFAULT 'running',
            input_summary VARCHAR(500) NULL,
            output_summary VARCHAR(500) NULL,
            error_message TEXT NULL,
            started_at DATETIME(6) NOT NULL,
            completed_at DATETIME(6) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_agent_runs_request_id (request_id),
            INDEX idx_agent_runs_course_created (user_id, course_id, created_at),
            INDEX idx_agent_runs_session_created (session_id, created_at),
            CONSTRAINT fk_agent_runs_agent FOREIGN KEY (agent_id) REFERENCES course_agents(id) ON DELETE CASCADE,
            CONSTRAINT fk_agent_runs_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_agent_runs_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_agent_runs_session FOREIGN KEY (session_id) REFERENCES chat_sessions(id) ON DELETE CASCADE,
            CONSTRAINT fk_agent_runs_user_message FOREIGN KEY (user_message_id)
                REFERENCES agent_chat_messages(id) ON DELETE SET NULL,
            CONSTRAINT fk_agent_runs_assistant_message FOREIGN KEY (assistant_message_id)
                REFERENCES agent_chat_messages(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_tool_calls (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            run_id BIGINT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            tool_name VARCHAR(100) NOT NULL,
            risk_level VARCHAR(30) NOT NULL DEFAULT 'read',
            arguments_json JSON NOT NULL,
            result_json JSON NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'running',
            error_message TEXT NULL,
            idempotency_key VARCHAR(100) NOT NULL,
            started_at DATETIME(6) NOT NULL,
            completed_at DATETIME(6) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_agent_tool_calls_idempotency (idempotency_key),
            INDEX idx_agent_tool_calls_run (run_id, id),
            INDEX idx_agent_tool_calls_course (user_id, course_id, created_at),
            CONSTRAINT fk_agent_tool_calls_run FOREIGN KEY (run_id) REFERENCES agent_runs(id) ON DELETE CASCADE,
            CONSTRAINT fk_agent_tool_calls_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_agent_tool_calls_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )


def _upgrade_course_vector_index(cursor) -> None:
    _add_column(cursor, "course_material_chunks", "content_hash", "CHAR(64) NULL")
    _add_column(cursor, "course_material_chunks", "indexed_at", "DATETIME NULL")
    _add_index(
        cursor,
        "course_material_chunks",
        "idx_material_chunks_hash",
        "material_id, content_hash",
    )
    cursor.execute(
        """
        UPDATE course_material_chunks
        SET content_hash = SHA2(chunk_text, 256), indexed_at = COALESCE(indexed_at, created_at)
        WHERE content_hash IS NULL
        """
    )
    _add_column(cursor, "knowledge_points", "embedding_json", "LONGTEXT NULL")
    _add_column(cursor, "knowledge_points", "embedding_model", "VARCHAR(120) NULL")
    _add_column(cursor, "knowledge_points", "embedding_hash", "CHAR(64) NULL")
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_point_relations (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            source_point_id INT NOT NULL,
            target_point_id INT NOT NULL,
            relation_type VARCHAR(40) NOT NULL DEFAULT 'prerequisite',
            confidence DECIMAL(5,4) NOT NULL DEFAULT 0.5000,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_knowledge_point_relation
                (course_id, source_point_id, target_point_id, relation_type),
            INDEX idx_knowledge_point_relations_course (user_id, course_id),
            CONSTRAINT fk_knowledge_point_relations_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_knowledge_point_relations_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_knowledge_point_relations_source FOREIGN KEY (source_point_id)
                REFERENCES knowledge_points(id) ON DELETE CASCADE,
            CONSTRAINT fk_knowledge_point_relations_target FOREIGN KEY (target_point_id)
                REFERENCES knowledge_points(id) ON DELETE CASCADE
        )
        """
    )


def _upgrade_external_resource_engine(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS external_resources (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            knowledge_point_id INT NULL,
            provider VARCHAR(40) NOT NULL,
            provider_resource_id VARCHAR(160) NULL,
            resource_type VARCHAR(40) NOT NULL DEFAULT 'video',
            canonical_url VARCHAR(1000) NOT NULL,
            url_hash CHAR(64) NOT NULL,
            title VARCHAR(500) NOT NULL,
            author VARCHAR(255) NULL,
            summary TEXT NULL,
            thumbnail_url VARCHAR(1000) NULL,
            duration_seconds INT NULL,
            published_at DATETIME NULL,
            language VARCHAR(20) NOT NULL DEFAULT 'zh-CN',
            relevance_score DECIMAL(7,6) NOT NULL DEFAULT 0,
            quality_score DECIMAL(7,6) NOT NULL DEFAULT 0,
            search_query VARCHAR(500) NULL,
            metadata_json JSON NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            last_checked_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_external_resource_url (user_id, course_id, url_hash),
            INDEX idx_external_resources_course (user_id, course_id, status, updated_at),
            INDEX idx_external_resources_point (knowledge_point_id, status),
            CONSTRAINT fk_external_resources_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_external_resources_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_external_resources_point FOREIGN KEY (knowledge_point_id)
                REFERENCES knowledge_points(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS resource_interactions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            resource_id BIGINT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            interaction_type VARCHAR(40) NOT NULL,
            value_json JSON NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            INDEX idx_resource_interactions_resource (resource_id, created_at),
            INDEX idx_resource_interactions_course (user_id, course_id, interaction_type, created_at),
            CONSTRAINT fk_resource_interactions_resource FOREIGN KEY (resource_id)
                REFERENCES external_resources(id) ON DELETE CASCADE,
            CONSTRAINT fk_resource_interactions_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_resource_interactions_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS external_resource_search_cache (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            query_hash CHAR(64) NOT NULL,
            query_text VARCHAR(500) NOT NULL,
            result_ids_json JSON NOT NULL,
            degraded BOOLEAN NOT NULL DEFAULT FALSE,
            warning VARCHAR(500) NULL,
            expires_at DATETIME NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_external_search_cache (user_id, course_id, query_hash),
            INDEX idx_external_search_cache_expiry (expires_at),
            CONSTRAINT fk_external_search_cache_user FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_external_search_cache_course FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )


def _upgrade_legacy_agent_message_sessions(cursor) -> None:
    cursor.execute(
        """
        SELECT user_id, course_id, MIN(created_at) AS first_message_at,
               MAX(created_at) AS last_message_at
        FROM agent_chat_messages
        WHERE session_id IS NULL
        GROUP BY user_id, course_id
        """
    )
    groups = list(cursor.fetchall())
    for group in groups:
        cursor.execute(
            """
            SELECT id FROM chat_sessions
            WHERE user_id = %s AND course_id <=> %s AND archived_at IS NULL
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (group["user_id"], group["course_id"]),
        )
        session = cursor.fetchone()
        if session is None:
            cursor.execute(
                """
                INSERT INTO chat_sessions
                    (user_id, course_id, title, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    group["user_id"],
                    group["course_id"],
                    "历史课程对话" if group["course_id"] is not None else "历史助手对话",
                    group["first_message_at"],
                    group["last_message_at"],
                ),
            )
            session_id = cursor.lastrowid
        else:
            session_id = session["id"]
        cursor.execute(
            """
            UPDATE agent_chat_messages
            SET session_id = %s
            WHERE user_id = %s AND course_id <=> %s AND session_id IS NULL
            """,
            (session_id, group["user_id"], group["course_id"]),
        )


def _upgrade_knowledge_point_semantics(cursor) -> None:
    _add_column(cursor, "knowledge_points", "summary", "TEXT NULL")
    _add_column(cursor, "knowledge_points", "examples_json", "JSON NULL")
    cursor.execute(
        """
        UPDATE knowledge_points
        SET summary = COALESCE(NULLIF(summary, ''), description),
            examples_json = COALESCE(examples_json, JSON_ARRAY()),
            embedding_hash = NULL
        WHERE summary IS NULL OR summary = '' OR examples_json IS NULL
        """
    )


def _upgrade_rag_quality_metadata(cursor) -> None:
    _add_column(cursor, "course_materials", "chunker_version", "VARCHAR(64) NULL")
    _add_column(cursor, "course_material_chunks", "heading_path", "TEXT NULL")
    _add_column(cursor, "course_material_chunks", "kb_ids_json", "JSON NULL")
    _add_column(
        cursor,
        "course_material_chunks",
        "document_type",
        "VARCHAR(40) NOT NULL DEFAULT 'content'",
    )
    _add_column(cursor, "course_material_chunks", "char_start", "INT NULL")
    _add_column(cursor, "course_material_chunks", "char_end", "INT NULL")
    _add_column(cursor, "course_material_chunks", "chunker_version", "VARCHAR(64) NULL")
    _add_column(cursor, "course_material_chunks", "estimated_tokens", "INT NULL")
    _add_column(cursor, "course_material_chunks", "embedding_hash", "CHAR(64) NULL")
    _add_index(
        cursor,
        "course_material_chunks",
        "idx_material_chunks_embedding_hash",
        "material_id, embedding_hash",
    )


def _upgrade_production_hardening(cursor) -> None:
    """Add durable coordination and normalized relationships without dropping data."""
    _add_column(cursor, "users", "is_active", "BOOLEAN NOT NULL DEFAULT TRUE")
    _add_column(cursor, "users", "token_version", "INT NOT NULL DEFAULT 0")
    _add_column(cursor, "users", "last_login_at", "DATETIME NULL")
    _add_column(cursor, "course_agents", "last_summarized_message_id", "INT NULL")
    _add_column(cursor, "knowledge_points", "status", "VARCHAR(30) NOT NULL DEFAULT 'active'")
    _add_index(cursor, "knowledge_points", "idx_knowledge_points_status", "user_id, course_id, status")
    _add_column(cursor, "agent_action_requests", "checkpoint_json", "JSON NULL")

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS evaluation_attempts (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            quiz_set_id INT NOT NULL,
            study_session_id INT NULL,
            attempt_key VARCHAR(120) NOT NULL,
            request_hash CHAR(64) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'evaluating',
            evaluation_id INT NULL,
            result_json JSON NULL,
            error_message TEXT NULL,
            started_at DATETIME(6) NOT NULL,
            completed_at DATETIME(6) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_evaluation_attempt_key (user_id, attempt_key),
            INDEX idx_evaluation_attempt_status (status, updated_at),
            CONSTRAINT fk_evaluation_attempt_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_evaluation_attempt_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_evaluation_attempt_quiz FOREIGN KEY (quiz_set_id)
                REFERENCES quiz_sets(id) ON DELETE CASCADE,
            CONSTRAINT fk_evaluation_attempt_session FOREIGN KEY (study_session_id)
                REFERENCES study_sessions(id) ON DELETE SET NULL,
            CONSTRAINT fk_evaluation_attempt_evaluation FOREIGN KEY (evaluation_id)
                REFERENCES learning_evaluations(id) ON DELETE SET NULL
        )
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS material_processing_jobs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            material_id INT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'queued',
            attempts INT NOT NULL DEFAULT 0,
            max_attempts INT NOT NULL DEFAULT 3,
            worker_id VARCHAR(100) NULL,
            lease_expires_at DATETIME(6) NULL,
            available_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            last_error TEXT NULL,
            started_at DATETIME(6) NULL,
            completed_at DATETIME(6) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_material_processing_job_material (material_id),
            INDEX idx_material_jobs_claim (status, available_at, lease_expires_at),
            CONSTRAINT fk_material_job_material FOREIGN KEY (material_id)
                REFERENCES course_materials(id) ON DELETE CASCADE,
            CONSTRAINT fk_material_job_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_material_job_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        INSERT INTO material_processing_jobs (material_id, user_id, course_id, status)
        SELECT id, user_id, course_id, 'queued'
        FROM course_materials
        WHERE course_id IS NOT NULL
          AND processing_status IN ('uploaded', 'parsing', 'indexing')
        ON DUPLICATE KEY UPDATE
            status = IF(status IN ('completed', 'running'), status, 'queued'),
            available_at = CURRENT_TIMESTAMP(6)
        """
    )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS knowledge_point_sources (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            knowledge_point_id INT NOT NULL,
            chunk_id INT NOT NULL,
            material_id INT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            evidence_type VARCHAR(30) NOT NULL DEFAULT 'extracted',
            confidence DECIMAL(5,4) NOT NULL DEFAULT 1.0000,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_knowledge_point_source (knowledge_point_id, chunk_id),
            INDEX idx_knowledge_sources_chunk (chunk_id, knowledge_point_id),
            INDEX idx_knowledge_sources_course (user_id, course_id, knowledge_point_id),
            CONSTRAINT fk_knowledge_source_point FOREIGN KEY (knowledge_point_id)
                REFERENCES knowledge_points(id) ON DELETE CASCADE,
            CONSTRAINT fk_knowledge_source_chunk FOREIGN KEY (chunk_id)
                REFERENCES course_material_chunks(id) ON DELETE CASCADE,
            CONSTRAINT fk_knowledge_source_material FOREIGN KEY (material_id)
                REFERENCES course_materials(id) ON DELETE CASCADE,
            CONSTRAINT fk_knowledge_source_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_knowledge_source_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )


def _upgrade_evaluation_attempt_scope(cursor) -> None:
    """Allow one quiz to be evaluated again inside distinct study sessions."""
    _add_column(cursor, "evaluation_attempts", "attempt_key", "VARCHAR(120) NULL")
    if not _table_exists(cursor, "evaluation_attempts"):
        return
    cursor.execute(
        """
        UPDATE evaluation_attempts
        SET attempt_key = CASE
            WHEN study_session_id IS NULL THEN CONCAT('quiz:', quiz_set_id)
            ELSE CONCAT('session:', study_session_id, ':quiz:', quiz_set_id)
        END
        WHERE attempt_key IS NULL OR attempt_key = ''
        """
    )
    cursor.execute("ALTER TABLE evaluation_attempts MODIFY COLUMN attempt_key VARCHAR(120) NOT NULL")
    _add_index(cursor, "evaluation_attempts", "idx_evaluation_attempt_user", "user_id")
    _add_index(cursor, "evaluation_attempts", "idx_evaluation_attempt_quiz_set", "quiz_set_id")
    _drop_index(cursor, "evaluation_attempts", "uk_evaluation_attempt_quiz")
    _add_unique_index(cursor, "evaluation_attempts", "uk_evaluation_attempt_key", "user_id, attempt_key")
    cursor.execute(
        """
        SELECT point.id AS point_id, point.user_id, point.course_id, point.source_chunk_ids
        FROM knowledge_points point
        WHERE point.source_chunk_ids IS NOT NULL
        """
    )
    for point in cursor.fetchall():
        try:
            chunk_ids = json.loads(point.get("source_chunk_ids") or "[]")
        except (TypeError, ValueError):
            chunk_ids = []
        for chunk_id in chunk_ids:
            if not str(chunk_id).isdigit():
                continue
            cursor.execute(
                """
                INSERT IGNORE INTO knowledge_point_sources
                    (knowledge_point_id, chunk_id, material_id, user_id, course_id)
                SELECT %s, chunk.id, chunk.material_id, %s, %s
                FROM course_material_chunks chunk
                JOIN course_materials material ON material.id = chunk.material_id
                WHERE chunk.id = %s AND chunk.user_id = %s
                  AND material.course_id = %s AND material.user_id = %s
                """,
                (
                    point["point_id"],
                    point["user_id"],
                    point["course_id"],
                    int(chunk_id),
                    point["user_id"],
                    point["course_id"],
                    point["user_id"],
                ),
            )

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_login_events (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            identifier_hash CHAR(64) NOT NULL,
            ip_hash CHAR(64) NOT NULL,
            succeeded BOOLEAN NOT NULL DEFAULT FALSE,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            INDEX idx_auth_login_identifier (identifier_hash, created_at),
            INDEX idx_auth_login_ip (ip_hash, created_at)
        )
        """
    )


def _upgrade_durable_agent_checkpoints(cursor) -> None:
    """Persist LangGraph checkpoints so interrupted tools survive restarts."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_graph_checkpoints (
            thread_id VARCHAR(160) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            checkpoint_ns VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            checkpoint_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            parent_checkpoint_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NULL,
            checkpoint_type VARCHAR(100) CHARACTER SET ascii NOT NULL,
            checkpoint_blob LONGBLOB NOT NULL,
            metadata_type VARCHAR(100) CHARACTER SET ascii NOT NULL,
            metadata_blob LONGBLOB NOT NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id),
            INDEX idx_agent_graph_checkpoint_latest
                (thread_id, checkpoint_ns, checkpoint_id)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_graph_checkpoint_blobs (
            thread_id VARCHAR(160) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            checkpoint_ns VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            channel_name VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            channel_version VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            value_type VARCHAR(100) CHARACTER SET ascii NOT NULL,
            value_blob LONGBLOB NOT NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            PRIMARY KEY (thread_id, checkpoint_ns, channel_name, channel_version)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_graph_checkpoint_writes (
            thread_id VARCHAR(160) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            checkpoint_ns VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            checkpoint_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            task_id VARCHAR(128) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            write_index INT NOT NULL,
            channel_name VARCHAR(255) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
            value_type VARCHAR(100) CHARACTER SET ascii NOT NULL,
            value_blob LONGBLOB NOT NULL,
            task_path VARCHAR(1000) NOT NULL DEFAULT '',
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, write_index),
            INDEX idx_agent_graph_writes_checkpoint
                (thread_id, checkpoint_ns, checkpoint_id)
        )
        """
    )


def _upgrade_persistent_rag_index(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS course_material_search_terms (
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            material_id INT NOT NULL,
            chunk_id INT NOT NULL,
            term VARCHAR(100) NOT NULL,
            term_frequency SMALLINT UNSIGNED NOT NULL DEFAULT 1,
            document_length INT UNSIGNED NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (user_id, course_id, term, chunk_id),
            INDEX idx_material_search_chunk (chunk_id),
            INDEX idx_material_search_material (material_id, chunk_id),
            CONSTRAINT fk_material_search_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_material_search_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_material_search_material FOREIGN KEY (material_id)
                REFERENCES course_materials(id) ON DELETE CASCADE,
            CONSTRAINT fk_material_search_chunk FOREIGN KEY (chunk_id)
                REFERENCES course_material_chunks(id) ON DELETE CASCADE
        )
        """
    )
    _add_column(cursor, "knowledge_points", "knowledge_level", "VARCHAR(30) NOT NULL DEFAULT 'concept'")
    _add_column(cursor, "knowledge_points", "parent_point_id", "INT NULL")
    _add_column(cursor, "knowledge_points", "category", "VARCHAR(150) NULL")
    _add_column(cursor, "knowledge_points", "extraction_confidence", "DECIMAL(5,4) NOT NULL DEFAULT 0.8000")
    _add_index(cursor, "knowledge_points", "idx_knowledge_hierarchy", "user_id, course_id, parent_point_id")
    _add_column(cursor, "knowledge_point_relations", "evidence_chunk_id", "INT NULL")
    _add_column(cursor, "knowledge_point_relations", "rationale", "VARCHAR(500) NULL")


def _upgrade_context_and_relation_cleanup(cursor) -> None:
    _add_column(cursor, "course_agent_memories", "embedding_json", "LONGTEXT NULL")
    _add_column(cursor, "course_agent_memories", "embedding_model", "VARCHAR(120) NULL")
    _add_column(cursor, "course_agent_memories", "embedding_hash", "CHAR(64) NULL")
    cursor.execute(
        """
        DELETE FROM knowledge_point_relations
        WHERE relation_type = 'prerequisite'
          AND confidence = 0.5500
          AND evidence_chunk_id IS NULL
          AND rationale IS NULL
        """
    )


def _upgrade_course_current_invariant(cursor) -> None:
    if not _table_exists(cursor, "courses"):
        return
    cursor.execute(
        "UPDATE courses SET is_current = FALSE WHERE status = 'archived' AND is_current = TRUE"
    )
    cursor.execute(
        """
        SELECT user_id
        FROM courses
        WHERE is_current = TRUE
        GROUP BY user_id
        HAVING COUNT(*) > 1
        """
    )
    duplicate_users = [int(row["user_id"]) for row in cursor.fetchall()]
    for user_id in duplicate_users:
        cursor.execute(
            """
            SELECT id
            FROM courses
            WHERE user_id = %s AND is_current = TRUE
            ORDER BY updated_at DESC, id DESC
            LIMIT 1
            """,
            (user_id,),
        )
        selected = cursor.fetchone()
        cursor.execute(
            """
            UPDATE courses
            SET is_current = FALSE
            WHERE user_id = %s AND is_current = TRUE AND id <> %s
            """,
            (user_id, selected["id"]),
        )
    _add_column(
        cursor,
        "courses",
        "current_user_id",
        "INT GENERATED ALWAYS AS (CASE WHEN is_current THEN user_id ELSE NULL END) VIRTUAL",
    )
    _add_unique_index(
        cursor,
        "courses",
        "uk_courses_one_current_per_user",
        "current_user_id",
    )


def _upgrade_user_timezone(cursor) -> None:
    _add_column(
        cursor,
        "users",
        "timezone",
        "VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai'",
    )


def _upgrade_durable_agent_actions(cursor) -> None:
    """Add durable request, tool-lease, and assistant-message coordination."""
    _add_column(cursor, "agent_runs", "client_request_id", "CHAR(36) NULL")
    _add_column(cursor, "agent_runs", "input_hash", "CHAR(64) NULL")
    _add_unique_index(
        cursor,
        "agent_runs",
        "uk_agent_runs_client_request",
        "user_id, client_request_id",
    )

    _add_column(cursor, "agent_tool_calls", "lease_owner", "VARCHAR(64) NULL")
    _add_column(cursor, "agent_tool_calls", "lease_expires_at", "DATETIME(6) NULL")
    _add_column(cursor, "agent_tool_calls", "heartbeat_at", "DATETIME(6) NULL")
    _add_column(
        cursor,
        "agent_tool_calls",
        "updated_at",
        "DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) "
        "ON UPDATE CURRENT_TIMESTAMP(6)",
    )
    _add_index(
        cursor,
        "agent_tool_calls",
        "idx_agent_tool_calls_lease",
        "status, lease_expires_at",
    )

    _add_column(cursor, "agent_chat_messages", "idempotency_key", "VARCHAR(160) NULL")
    _add_unique_index(
        cursor,
        "agent_chat_messages",
        "uk_agent_chat_message_idempotency",
        "user_id, idempotency_key",
    )


def _upgrade_general_agent_run_idempotency(cursor) -> None:
    """Allow the existing durable run ledger to represent general chat requests."""
    _modify_column(cursor, "agent_runs", "agent_id", "BIGINT NULL")
    _modify_column(cursor, "agent_runs", "course_id", "INT NULL")


def _upgrade_learning_roadmaps(cursor) -> None:
    """Add durable staged roadmaps without replacing the daily study plan."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_roadmaps (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            version INT NOT NULL DEFAULT 1,
            generation_method VARCHAR(60) NOT NULL DEFAULT 'rules_v1',
            goal_snapshot VARCHAR(500) NOT NULL DEFAULT '',
            target_date DATE NULL,
            daily_minutes INT NOT NULL DEFAULT 30,
            last_error TEXT NULL,
            generated_at DATETIME NULL,
            last_adjusted_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_learning_roadmaps_user_course (user_id, course_id),
            INDEX idx_learning_roadmaps_status (user_id, status),
            CONSTRAINT fk_learning_roadmaps_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_roadmaps_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS roadmap_generation_jobs (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            roadmap_id BIGINT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            idempotency_key VARCHAR(160) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            attempt INT NOT NULL DEFAULT 1,
            error_message TEXT NULL,
            started_at DATETIME NULL,
            completed_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_roadmap_generation_job_key (user_id, idempotency_key),
            INDEX idx_roadmap_generation_jobs_status (status, updated_at),
            CONSTRAINT fk_roadmap_generation_jobs_roadmap FOREIGN KEY (roadmap_id)
                REFERENCES learning_roadmaps(id) ON DELETE CASCADE,
            CONSTRAINT fk_roadmap_generation_jobs_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_roadmap_generation_jobs_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_roadmap_stages (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            roadmap_id BIGINT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            position INT NOT NULL,
            name VARCHAR(160) NOT NULL,
            goal VARCHAR(500) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            progress DECIMAL(5,2) NOT NULL DEFAULT 0.00,
            estimated_days INT NOT NULL DEFAULT 1,
            completion_condition VARCHAR(500) NOT NULL,
            recommended_content_json LONGTEXT NULL,
            adaptation_reason VARCHAR(500) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uk_learning_roadmap_stage_position (roadmap_id, position),
            INDEX idx_learning_roadmap_stages_course (user_id, course_id, status),
            CONSTRAINT fk_learning_roadmap_stages_roadmap FOREIGN KEY (roadmap_id)
                REFERENCES learning_roadmaps(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_roadmap_stages_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_roadmap_stages_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS roadmap_stage_points (
            stage_id BIGINT NOT NULL,
            knowledge_point_id INT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            sort_order INT NOT NULL DEFAULT 0,
            required_mastery DECIMAL(5,2) NOT NULL DEFAULT 70.00,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (stage_id, knowledge_point_id),
            INDEX idx_roadmap_stage_points_course (user_id, course_id),
            CONSTRAINT fk_roadmap_stage_points_stage FOREIGN KEY (stage_id)
                REFERENCES learning_roadmap_stages(id) ON DELETE CASCADE,
            CONSTRAINT fk_roadmap_stage_points_knowledge FOREIGN KEY (knowledge_point_id)
                REFERENCES knowledge_points(id) ON DELETE CASCADE,
            CONSTRAINT fk_roadmap_stage_points_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_roadmap_stage_points_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS roadmap_stage_sessions (
            stage_id BIGINT NOT NULL,
            study_session_id INT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            link_reason VARCHAR(255) NOT NULL DEFAULT 'daily_plan',
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (stage_id, study_session_id),
            INDEX idx_roadmap_stage_sessions_course (user_id, course_id),
            CONSTRAINT fk_roadmap_stage_sessions_stage FOREIGN KEY (stage_id)
                REFERENCES learning_roadmap_stages(id) ON DELETE CASCADE,
            CONSTRAINT fk_roadmap_stage_sessions_session FOREIGN KEY (study_session_id)
                REFERENCES study_sessions(id) ON DELETE CASCADE,
            CONSTRAINT fk_roadmap_stage_sessions_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_roadmap_stage_sessions_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS roadmap_adjustments (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            roadmap_id BIGINT NOT NULL,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            trigger_type VARCHAR(40) NOT NULL,
            trigger_id BIGINT NULL,
            idempotency_key VARCHAR(160) NOT NULL,
            reason VARCHAR(500) NOT NULL,
            details_json LONGTEXT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE KEY uk_roadmap_adjustment_key (user_id, idempotency_key),
            INDEX idx_roadmap_adjustments_course (user_id, course_id, created_at),
            CONSTRAINT fk_roadmap_adjustments_roadmap FOREIGN KEY (roadmap_id)
                REFERENCES learning_roadmaps(id) ON DELETE CASCADE,
            CONSTRAINT fk_roadmap_adjustments_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_roadmap_adjustments_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        )
        """
    )


def _upgrade_memory_transparency(cursor) -> None:
    """Expose memory origin and user-controlled inclusion without deleting history."""
    _add_column(
        cursor,
        "course_agent_memories",
        "source_type",
        "VARCHAR(30) NOT NULL DEFAULT 'manual'",
    )
    _add_column(
        cursor,
        "course_agent_memories",
        "enabled",
        "BOOLEAN NOT NULL DEFAULT TRUE",
    )
    _add_index(
        cursor,
        "course_agent_memories",
        "idx_course_agent_memories_visibility",
        "user_id, course_id, status, enabled, memory_type",
    )


def _upgrade_two_tier_learning_memory(cursor) -> None:
    """Add durable automatic memory extraction and user-level learning profiles."""
    _add_column(cursor, "course_agent_memories", "auto_generated", "BOOLEAN NOT NULL DEFAULT FALSE")
    _add_column(cursor, "course_agent_memories", "confidence", "DECIMAL(5,4) NULL")
    _add_column(cursor, "course_agent_memories", "evidence_json", "LONGTEXT NULL")
    _add_column(cursor, "course_agent_memories", "last_observed_at", "DATETIME(6) NULL")
    _add_index(
        cursor,
        "course_agent_memories",
        "idx_course_agent_memories_automatic",
        "user_id, course_id, status, enabled, auto_generated, updated_at",
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS learning_memory_jobs (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            job_type VARCHAR(40) NOT NULL,
            user_id INT NOT NULL,
            course_id INT NULL,
            agent_id BIGINT NULL,
            session_id BIGINT NULL,
            source_message_id INT NULL,
            idempotency_key VARCHAR(180) NOT NULL,
            payload_json LONGTEXT NULL,
            result_json LONGTEXT NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'queued',
            attempts INT NOT NULL DEFAULT 0,
            max_attempts INT NOT NULL DEFAULT 3,
            available_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            worker_id VARCHAR(180) NULL,
            lease_expires_at DATETIME(6) NULL,
            last_error TEXT NULL,
            started_at DATETIME(6) NULL,
            completed_at DATETIME(6) NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            UNIQUE KEY uk_learning_memory_jobs_idempotency (idempotency_key),
            INDEX idx_learning_memory_jobs_claim (status, available_at, lease_expires_at),
            INDEX idx_learning_memory_jobs_user (user_id, job_type, created_at),
            CONSTRAINT fk_learning_memory_jobs_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_memory_jobs_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_memory_jobs_agent FOREIGN KEY (agent_id)
                REFERENCES course_agents(id) ON DELETE SET NULL,
            CONSTRAINT fk_learning_memory_jobs_session FOREIGN KEY (session_id)
                REFERENCES chat_sessions(id) ON DELETE SET NULL,
            CONSTRAINT fk_learning_memory_jobs_message FOREIGN KEY (source_message_id)
                REFERENCES agent_chat_messages(id) ON DELETE SET NULL
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_memory_settings (
            user_id INT PRIMARY KEY,
            course_auto_memory_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            cross_course_profile_enabled BOOLEAN NOT NULL DEFAULT FALSE,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT fk_user_memory_settings_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_learning_profiles (
            id BIGINT PRIMARY KEY AUTO_INCREMENT,
            user_id INT NOT NULL,
            profile_json LONGTEXT NOT NULL,
            source_watermark BIGINT NULL,
            source_memory_count INT NOT NULL DEFAULT 0,
            source_course_count INT NOT NULL DEFAULT 0,
            version INT NOT NULL DEFAULT 1,
            status VARCHAR(20) NOT NULL DEFAULT 'active',
            generated_at DATETIME(6) NULL,
            last_error TEXT NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            UNIQUE KEY uk_user_learning_profiles_user (user_id),
            INDEX idx_user_learning_profiles_status (user_id, status, updated_at),
            CONSTRAINT fk_user_learning_profiles_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )


def _upgrade_user_llm_configs(cursor) -> None:
    """Store per-user OpenAI-compatible model configuration without plaintext keys."""
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS user_llm_configs (
            user_id INT PRIMARY KEY,
            provider VARCHAR(40) NOT NULL DEFAULT 'openai_compatible',
            enabled BOOLEAN NOT NULL DEFAULT FALSE,
            base_url VARCHAR(500) NOT NULL,
            model VARCHAR(160) NOT NULL,
            api_key_ciphertext TEXT NOT NULL,
            api_key_hint VARCHAR(24) NOT NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
            CONSTRAINT fk_user_llm_configs_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )


MIGRATIONS = [
    Migration("0001", "non_destructive_baseline", _upgrade_baseline),
    Migration("0002", "course_learning_foundation", _upgrade_course_learning_foundation),
    Migration("0003", "backfill_courses", _upgrade_backfill_courses),
    Migration("0004", "material_processing_metadata", _upgrade_material_processing_metadata),
    Migration("0005", "learning_loop_metadata", _upgrade_learning_loop_metadata),
    Migration("0006", "agent_session_safety", _upgrade_agent_session_safety),
    Migration("0007", "course_agent_foundation", _upgrade_course_agent_foundation),
    Migration("0008", "course_vector_index", _upgrade_course_vector_index),
    Migration("0009", "external_resource_engine", _upgrade_external_resource_engine),
    Migration("0010", "legacy_agent_message_sessions", _upgrade_legacy_agent_message_sessions),
    Migration("0011", "knowledge_point_semantics", _upgrade_knowledge_point_semantics),
    Migration("0012", "rag_quality_metadata", _upgrade_rag_quality_metadata),
    Migration("0013", "production_hardening", _upgrade_production_hardening),
    Migration("0014", "evaluation_attempt_scope", _upgrade_evaluation_attempt_scope),
    Migration("0015", "durable_agent_checkpoints", _upgrade_durable_agent_checkpoints),
    Migration("0016", "persistent_rag_index", _upgrade_persistent_rag_index),
    Migration("0017", "context_and_relation_cleanup", _upgrade_context_and_relation_cleanup),
    Migration("0018", "course_current_invariant", _upgrade_course_current_invariant),
    Migration("0019", "user_timezone", _upgrade_user_timezone),
    Migration("0020", "durable_agent_actions", _upgrade_durable_agent_actions),
    Migration("0021", "general_agent_run_idempotency", _upgrade_general_agent_run_idempotency),
    Migration("0022", "learning_roadmaps", _upgrade_learning_roadmaps),
    Migration("0023", "memory_transparency", _upgrade_memory_transparency),
    Migration("0024", "two_tier_learning_memory", _upgrade_two_tier_learning_memory),
    Migration("0025", "user_llm_configs", _upgrade_user_llm_configs),
]


def _ensure_migration_table(cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version VARCHAR(50) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def run_migrations(connection=None, target_version: str | None = None) -> list[str]:
    owns_connection = connection is None
    if connection is None:
        connection = get_conn()
    selected_migrations = MIGRATIONS
    if target_version is not None:
        target_indexes = [
            index for index, migration in enumerate(MIGRATIONS) if migration.version == target_version
        ]
        if not target_indexes:
            raise ValueError(f"Unknown migration target: {target_version}")
        selected_migrations = MIGRATIONS[: target_indexes[0] + 1]
    cursor = connection.cursor()
    applied = []
    try:
        _ensure_migration_table(cursor)
        connection.commit()
        cursor.execute("SELECT version FROM schema_migrations")
        completed = {row["version"] for row in cursor.fetchall()}

        for migration in selected_migrations:
            if migration.version in completed:
                continue
            migration.upgrade(cursor)
            cursor.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (%s, %s)",
                (migration.version, migration.name),
            )
            connection.commit()
            applied.append(migration.version)
        return applied
    except Exception:
        connection.rollback()
        raise
    finally:
        cursor.close()
        if owns_connection:
            connection.close()


if __name__ == "__main__":
    versions = run_migrations()
    if versions:
        print("Applied migrations: " + ", ".join(versions))
    else:
        print("Database is up to date")
