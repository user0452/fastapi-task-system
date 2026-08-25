"""Complete the evidence-backed Adaptive Tutor stage-two storage boundary.

The previous migration intentionally introduced the core V2 tables without
changing historical tables.  This migration only adds stage-two fields and
new bounded records for import previews and explicit Tutor Checks.  Existing
history remains upgradeable and no old table is dropped here.
"""

from alembic import op

revision = "20260825_13"
down_revision = "20260825_12"
branch_labels = None
depends_on = None


def _execute(statement: str, params: tuple | None = None) -> None:
    op.get_bind().exec_driver_sql(statement, params or ())


def _column_exists(table: str, column: str) -> bool:
    result = op.get_bind().exec_driver_sql(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = %s AND column_name = %s
        """,
        (table, column),
    ).fetchone()
    return bool(result and int(result[0] if not hasattr(result, "_mapping") else result._mapping["total"]))


def _index_exists(table: str, index: str) -> bool:
    result = op.get_bind().exec_driver_sql(
        """
        SELECT COUNT(*) AS total
        FROM information_schema.statistics
        WHERE table_schema = DATABASE() AND table_name = %s AND index_name = %s
        """,
        (table, index),
    ).fetchone()
    return bool(result and int(result[0] if not hasattr(result, "_mapping") else result._mapping["total"]))


def _add_column(table: str, column: str, definition: str) -> None:
    if not _column_exists(table, column):
        _execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {definition}")


def _add_index(table: str, index: str, definition: str) -> None:
    if not _index_exists(table, index):
        _execute(f"ALTER TABLE `{table}` ADD INDEX `{index}` {definition}")


def upgrade() -> None:
    _execute(
        """
        CREATE TABLE IF NOT EXISTS question_import_batches (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            filename VARCHAR(255) NOT NULL,
            file_type VARCHAR(20) NOT NULL,
            source_type VARCHAR(30) NOT NULL DEFAULT 'user_upload',
            idempotency_key VARCHAR(160) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'preview',
            parsed_count INT NOT NULL DEFAULT 0,
            matched_count INT NOT NULL DEFAULT 0,
            unmatched_count INT NOT NULL DEFAULT 0,
            invalid_count INT NOT NULL DEFAULT 0,
            items_json JSON NOT NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            completed_at DATETIME(6) NULL,
            UNIQUE KEY uk_question_import_batch (user_id, course_id, idempotency_key),
            INDEX idx_question_import_course (user_id, course_id, created_at),
            CONSTRAINT fk_question_import_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_question_import_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS tutor_checks (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            objective_id BIGINT NOT NULL,
            action_id BIGINT NULL,
            question TEXT NOT NULL,
            reference_answer TEXT NOT NULL,
            rubric TEXT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'open',
            response TEXT NULL,
            score DECIMAL(5,4) NULL,
            grader_type VARCHAR(40) NULL,
            grader_version VARCHAR(80) NULL,
            grader_model VARCHAR(120) NULL,
            grader_prompt_version VARCHAR(100) NULL,
            evidence_id BIGINT NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            submitted_at DATETIME(6) NULL,
            INDEX idx_tutor_check_course (user_id, course_id, objective_id, created_at),
            CONSTRAINT fk_tutor_check_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_tutor_check_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_tutor_check_objective FOREIGN KEY (objective_id)
                REFERENCES learning_objectives(id) ON DELETE CASCADE,
            CONSTRAINT fk_tutor_check_action FOREIGN KEY (action_id)
                REFERENCES learning_actions(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )

    _add_column("questions", "options_json", "JSON NULL AFTER question_type")
    _add_column("questions", "tolerance", "DECIMAL(12,6) NULL AFTER answer")
    _add_column("questions", "source_file", "VARCHAR(255) NULL AFTER source_url")
    _add_column("questions", "import_batch_id", "BIGINT NULL AFTER source_file")
    _add_column("questions", "raw_provenance_json", "JSON NULL AFTER import_batch_id")
    _add_column("questions", "validation_json", "JSON NULL AFTER raw_provenance_json")
    _add_column("question_attempts", "grader_model", "VARCHAR(120) NULL AFTER grader_version")
    _add_column("question_attempts", "grader_prompt_version", "VARCHAR(100) NULL AFTER grader_model")
    _add_column("question_attempts", "metadata_json", "JSON NULL AFTER feedback")
    _add_column("question_attempts", "idempotency_key", "VARCHAR(160) NULL AFTER metadata_json")
    _add_column("learning_evidence", "action_id", "BIGINT NULL AFTER attempt_id")
    _add_column("learning_evidence", "idempotency_key", "VARCHAR(160) NULL AFTER action_id")
    _add_column("learning_evidence", "grader_model", "VARCHAR(120) NULL AFTER grader_version")
    _add_column("learning_evidence", "grader_prompt_version", "VARCHAR(100) NULL AFTER grader_model")
    _add_column("learning_evidence", "metadata_json", "JSON NULL AFTER update_reason")
    _add_column("student_objective_states", "quantity_confidence", "DECIMAL(5,4) NOT NULL DEFAULT 0.0000 AFTER confidence")
    _add_column("student_objective_states", "consistency_confidence", "DECIMAL(5,4) NOT NULL DEFAULT 0.0000 AFTER quantity_confidence")
    _add_column("student_objective_states", "diversity_confidence", "DECIMAL(5,4) NOT NULL DEFAULT 0.0000 AFTER consistency_confidence")
    _add_column("student_objective_states", "quality_confidence", "DECIMAL(5,4) NOT NULL DEFAULT 0.0000 AFTER diversity_confidence")
    _add_column("student_objective_states", "recency_confidence", "DECIMAL(5,4) NOT NULL DEFAULT 0.0000 AFTER quality_confidence")
    _add_column("misconceptions", "success_evidence_count", "INT NOT NULL DEFAULT 0 AFTER occurrence_count")
    _add_column("misconceptions", "failure_evidence_count", "INT NOT NULL DEFAULT 0 AFTER success_evidence_count")
    _add_column("misconceptions", "last_confirmed_at", "DATETIME(6) NULL AFTER last_seen_at")

    if not _index_exists("questions", "idx_questions_import_batch"):
        _execute("ALTER TABLE questions ADD INDEX idx_questions_import_batch (import_batch_id)")
    if not _index_exists("questions", "idx_questions_source_file"):
        _execute("ALTER TABLE questions ADD INDEX idx_questions_source_file (source_file)")
    if not _index_exists("tutor_checks", "idx_tutor_check_status"):
        _execute("ALTER TABLE tutor_checks ADD INDEX idx_tutor_check_status (user_id, course_id, status)")
    if not _index_exists("learning_evidence", "idx_learning_evidence_idempotency"):
        _execute("ALTER TABLE learning_evidence ADD UNIQUE INDEX idx_learning_evidence_idempotency (user_id, course_id, source_type, idempotency_key)")


def downgrade() -> None:
    raise RuntimeError("Adaptive Tutor stage-two history cannot be safely downgraded")
