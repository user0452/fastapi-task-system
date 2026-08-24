"""Add the evidence-backed Adaptive Tutor domain.

The historical schema is intentionally left in place for compatibility with
existing installations.  V2 reads and writes these tables as its product
surface; the old knowledge-point, roadmap, and generic-memory tables are not
part of the new learning decision path.
"""

from alembic import op

revision = "20260825_12"
down_revision = "20260807_11"
branch_labels = None
depends_on = None


def _execute(statement: str) -> None:
    op.get_bind().exec_driver_sql(statement)


def upgrade() -> None:
    _execute(
        """
        CREATE TABLE IF NOT EXISTS curriculum_builds (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            material_id INT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'pending',
            extraction_confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
            model VARCHAR(120) NULL,
            prompt_version VARCHAR(80) NULL,
            error_message TEXT NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            completed_at DATETIME(6) NULL,
            INDEX idx_curriculum_build_course (user_id, course_id, created_at),
            INDEX idx_curriculum_build_status (status, created_at),
            CONSTRAINT fk_curriculum_build_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_curriculum_build_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_curriculum_build_material FOREIGN KEY (material_id)
                REFERENCES course_materials(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS learning_objectives (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            title VARCHAR(255) NOT NULL,
            description TEXT NOT NULL,
            required_ability VARCHAR(500) NOT NULL,
            importance DECIMAL(5,4) NOT NULL DEFAULT 0.5000,
            difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            extraction_confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
            curriculum_version VARCHAR(80) NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),
            UNIQUE KEY uk_learning_objective_title (user_id, course_id, title),
            INDEX idx_learning_objective_course (user_id, course_id, status, importance),
            CONSTRAINT fk_learning_objective_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_objective_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS objective_relations (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            source_objective_id BIGINT NOT NULL,
            target_objective_id BIGINT NOT NULL,
            relation_type VARCHAR(30) NOT NULL,
            confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
            rationale VARCHAR(500) NULL,
            evidence_chunk_id INT NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            UNIQUE KEY uk_objective_relation (source_objective_id, target_objective_id, relation_type),
            INDEX idx_objective_relation_target (course_id, target_objective_id, relation_type),
            CONSTRAINT fk_objective_relation_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_objective_relation_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_objective_relation_source FOREIGN KEY (source_objective_id)
                REFERENCES learning_objectives(id) ON DELETE CASCADE,
            CONSTRAINT fk_objective_relation_target FOREIGN KEY (target_objective_id)
                REFERENCES learning_objectives(id) ON DELETE CASCADE,
            CONSTRAINT fk_objective_relation_chunk FOREIGN KEY (evidence_chunk_id)
                REFERENCES course_material_chunks(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS objective_evidence (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            objective_id BIGINT NOT NULL,
            material_id INT NOT NULL,
            chunk_id INT NOT NULL,
            confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            UNIQUE KEY uk_objective_evidence (objective_id, chunk_id),
            INDEX idx_objective_evidence_course (user_id, course_id, objective_id),
            CONSTRAINT fk_objective_evidence_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_objective_evidence_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_objective_evidence_objective FOREIGN KEY (objective_id)
                REFERENCES learning_objectives(id) ON DELETE CASCADE,
            CONSTRAINT fk_objective_evidence_material FOREIGN KEY (material_id)
                REFERENCES course_materials(id) ON DELETE CASCADE,
            CONSTRAINT fk_objective_evidence_chunk FOREIGN KEY (chunk_id)
                REFERENCES course_material_chunks(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS questions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            content TEXT NOT NULL,
            question_type VARCHAR(30) NOT NULL DEFAULT 'short_answer',
            answer TEXT NOT NULL,
            rubric TEXT NULL,
            explanation TEXT NULL,
            difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
            source_type VARCHAR(30) NOT NULL,
            source_material_id INT NULL,
            source_url VARCHAR(1000) NULL,
            quality_score DECIMAL(5,4) NOT NULL DEFAULT 0.5000,
            status VARCHAR(30) NOT NULL DEFAULT 'active',
            model VARCHAR(120) NULL,
            prompt_version VARCHAR(80) NULL,
            generation_context_json JSON NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),
            INDEX idx_questions_course (user_id, course_id, status, difficulty),
            INDEX idx_questions_source (course_id, source_type),
            CONSTRAINT fk_questions_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_questions_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_questions_material FOREIGN KEY (source_material_id)
                REFERENCES course_materials(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS question_objectives (
            question_id BIGINT NOT NULL,
            objective_id BIGINT NOT NULL,
            relevance DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
            coverage_type VARCHAR(30) NOT NULL DEFAULT 'direct',
            confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            PRIMARY KEY (question_id, objective_id),
            INDEX idx_question_objective_target (objective_id, confidence),
            CONSTRAINT fk_question_objective_question FOREIGN KEY (question_id)
                REFERENCES questions(id) ON DELETE CASCADE,
            CONSTRAINT fk_question_objective_objective FOREIGN KEY (objective_id)
                REFERENCES learning_objectives(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS learning_actions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            objective_id BIGINT NOT NULL,
            action_type VARCHAR(40) NOT NULL,
            priority DECIMAL(8,4) NOT NULL DEFAULT 0.0000,
            reason TEXT NOT NULL,
            expected_minutes INT NOT NULL DEFAULT 8,
            desired_difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
            question_id BIGINT NULL,
            policy_version VARCHAR(80) NOT NULL,
            status VARCHAR(30) NOT NULL DEFAULT 'queued',
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            started_at DATETIME(6) NULL,
            completed_at DATETIME(6) NULL,
            INDEX idx_learning_actions_queue (user_id, course_id, status, priority, created_at),
            INDEX idx_learning_actions_objective (objective_id, created_at),
            CONSTRAINT fk_learning_action_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_action_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_action_objective FOREIGN KEY (objective_id)
                REFERENCES learning_objectives(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_action_question FOREIGN KEY (question_id)
                REFERENCES questions(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS question_attempts (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            question_id BIGINT NOT NULL,
            action_id BIGINT NULL,
            response TEXT NOT NULL,
            score DECIMAL(5,4) NOT NULL,
            grader_type VARCHAR(40) NOT NULL,
            grader_version VARCHAR(80) NOT NULL,
            feedback TEXT NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            INDEX idx_question_attempt_course (user_id, course_id, question_id, created_at),
            CONSTRAINT fk_question_attempt_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_question_attempt_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_question_attempt_question FOREIGN KEY (question_id)
                REFERENCES questions(id) ON DELETE CASCADE,
            CONSTRAINT fk_question_attempt_action FOREIGN KEY (action_id)
                REFERENCES learning_actions(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS learning_evidence (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            objective_id BIGINT NOT NULL,
            source_type VARCHAR(30) NOT NULL,
            question_id BIGINT NULL,
            attempt_id BIGINT NULL,
            response TEXT NULL,
            score DECIMAL(5,4) NOT NULL,
            difficulty VARCHAR(20) NOT NULL DEFAULT 'medium',
            grader_type VARCHAR(40) NOT NULL,
            grader_version VARCHAR(80) NOT NULL,
            misconception_code VARCHAR(100) NULL,
            misconception_text VARCHAR(500) NULL,
            misconception_confidence DECIMAL(5,4) NULL,
            mastery_before DECIMAL(5,4) NULL,
            mastery_after DECIMAL(5,4) NULL,
            confidence_before DECIMAL(5,4) NULL,
            confidence_after DECIMAL(5,4) NULL,
            update_reason VARCHAR(800) NULL,
            created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            INDEX idx_learning_evidence_state (user_id, course_id, objective_id, created_at),
            INDEX idx_learning_evidence_misconception (objective_id, misconception_code, created_at),
            CONSTRAINT fk_learning_evidence_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_evidence_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_evidence_objective FOREIGN KEY (objective_id)
                REFERENCES learning_objectives(id) ON DELETE CASCADE,
            CONSTRAINT fk_learning_evidence_question FOREIGN KEY (question_id)
                REFERENCES questions(id) ON DELETE SET NULL,
            CONSTRAINT fk_learning_evidence_attempt FOREIGN KEY (attempt_id)
                REFERENCES question_attempts(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS student_objective_states (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            objective_id BIGINT NOT NULL,
            mastery DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
            confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
            attempt_count INT NOT NULL DEFAULT 0,
            correct_count INT NOT NULL DEFAULT 0,
            incorrect_count INT NOT NULL DEFAULT 0,
            success_streak INT NOT NULL DEFAULT 0,
            failure_streak INT NOT NULL DEFAULT 0,
            last_practiced_at DATETIME(6) NULL,
            last_success_at DATETIME(6) NULL,
            last_failure_at DATETIME(6) NULL,
            state VARCHAR(30) NOT NULL DEFAULT 'unknown',
            model_version VARCHAR(80) NOT NULL DEFAULT 'bkt-inspired-v1',
            updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
                ON UPDATE CURRENT_TIMESTAMP(6),
            UNIQUE KEY uk_student_objective_state (user_id, course_id, objective_id),
            INDEX idx_student_objective_queue (user_id, course_id, state, mastery, confidence),
            CONSTRAINT fk_student_objective_state_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_student_objective_state_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_student_objective_state_objective FOREIGN KEY (objective_id)
                REFERENCES learning_objectives(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )
    _execute(
        """
        CREATE TABLE IF NOT EXISTS misconceptions (
            id BIGINT AUTO_INCREMENT PRIMARY KEY,
            user_id INT NOT NULL,
            course_id INT NOT NULL,
            objective_id BIGINT NOT NULL,
            code VARCHAR(100) NOT NULL,
            description VARCHAR(500) NOT NULL,
            confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
            occurrence_count INT NOT NULL DEFAULT 1,
            first_seen_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            last_seen_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
            resolved_at DATETIME(6) NULL,
            UNIQUE KEY uk_misconception (user_id, course_id, objective_id, code),
            INDEX idx_misconception_active (user_id, course_id, objective_id, resolved_at, last_seen_at),
            CONSTRAINT fk_misconception_user FOREIGN KEY (user_id)
                REFERENCES users(id) ON DELETE CASCADE,
            CONSTRAINT fk_misconception_course FOREIGN KEY (course_id)
                REFERENCES courses(id) ON DELETE CASCADE,
            CONSTRAINT fk_misconception_objective FOREIGN KEY (objective_id)
                REFERENCES learning_objectives(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
    )


def downgrade() -> None:
    # V2 data is user learning history.  Automatic destructive downgrade is
    # intentionally disabled; a future data-export migration can be explicit.
    raise RuntimeError("Adaptive learning history cannot be safely downgraded")
