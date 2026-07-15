CREATE DATABASE IF NOT EXISTS task_db2
DEFAULT CHARACTER SET utf8mb4
DEFAULT COLLATE utf8mb4_unicode_ci;

USE task_db2;

DROP TABLE IF EXISTS agent_chat_messages;
DROP TABLE IF EXISTS learning_evaluations;
DROP TABLE IF EXISTS course_material_chunks;
DROP TABLE IF EXISTS course_materials;
DROP TABLE IF EXISTS operation_logs;
DROP TABLE IF EXISTS student_profiles;
DROP TABLE IF EXISTS learning_resources;
DROP TABLE IF EXISTS tasks;
DROP TABLE IF EXISTS quiz_questions;
DROP TABLE IF EXISTS quiz_sets;
DROP TABLE IF EXISTS users;

CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE tasks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(20) NOT NULL DEFAULT 'todo',
    priority VARCHAR(20) NOT NULL DEFAULT 'medium',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_user_id (user_id),
    INDEX idx_user_status (user_id, status),

    CONSTRAINT fk_tasks_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE TABLE operation_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    action VARCHAR(100) NOT NULL,
    target_type VARCHAR(50),
    target_id INT,
    detail TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_logs_user_id (user_id),
    INDEX idx_logs_action (action),

    CONSTRAINT fk_logs_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE TABLE student_profiles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL UNIQUE,
    profile_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_profiles_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE TABLE learning_resources (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    course_name VARCHAR(100) NOT NULL,
    topic VARCHAR(100) NOT NULL,
    resource_type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,
    resource_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_resources_user_id (user_id),
    INDEX idx_resources_course_topic (user_id, course_name, topic),

    CONSTRAINT fk_resources_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE TABLE course_materials (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    course_name VARCHAR(100) NOT NULL,
    title VARCHAR(255) NOT NULL,
    content LONGTEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_materials_user_id (user_id),
    INDEX idx_materials_course_name (user_id, course_name),

    CONSTRAINT fk_materials_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

CREATE TABLE course_material_chunks (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    material_id INT NOT NULL,
    course_name VARCHAR(100) NOT NULL,
    chunk_index INT NOT NULL,
    chunk_text TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_chunks_user_course (user_id, course_name),
    INDEX idx_chunks_material_id (material_id),

    CONSTRAINT fk_chunks_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_chunks_material
        FOREIGN KEY (material_id)
        REFERENCES course_materials(id)
        ON DELETE CASCADE
);

CREATE TABLE agent_chat_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    role VARCHAR(20) NOT NULL,
    content TEXT NOT NULL,
    tool_calls TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_agent_chat_user_id (user_id),
    INDEX idx_agent_chat_user_created (user_id, created_at),

    CONSTRAINT fk_agent_chat_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

create table quiz_sets (
    id int auto_increment primary key,
    user_id int not null,
    title varchar(255) not null,
    course_name varchar(100) not null,
    topic varchar(100) not null,
    quiz_json text not null,
    created_at datetime default current_timestamp,

    index idx_quiz_sets_user_id (user_id),
    index idx_quiz_sets_course_topic (user_id, course_name, topic),

    constraint fk_quiz_sets_user
                       foreign key (user_id)
                       references users(id)
                       on delete cascade
);

CREATE TABLE learning_evaluations (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    quiz_set_id INT NOT NULL,
    score INT NOT NULL,
    level VARCHAR(50) NOT NULL,
    weak_points_json TEXT,
    suggestions_json TEXT,
    evaluation_json TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_evaluations_user_id (user_id),
    INDEX idx_evaluations_quiz_set_id (quiz_set_id),
    INDEX idx_evaluations_score (score),

    CONSTRAINT fk_evaluations_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE,

    CONSTRAINT fk_evaluations_quiz_set
        FOREIGN KEY (quiz_set_id)
        REFERENCES quiz_sets(id)
        ON DELETE CASCADE
);

create table quiz_questions (
    id int auto_increment primary key,
    quiz_set_id int not null,
    question_type varchar(50) not null,
    question varchar(255) not null,
    answer varchar(255) not null,
    difficulty varchar(20) not null,
    created_at datetime default current_timestamp,

    index idx_questions_quiz_set_id (quiz_set_id),
    index idx_questions_difficulty (difficulty),
    constraint fk_questions_quiz_set
                            foreign key (quiz_set_id)
                            references quiz_sets(id)
                            on delete cascade
);

-- AI 长期记忆表
CREATE TABLE ai_memories (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,

    -- 记忆分类
    memory_type ENUM('episodic', 'semantic', 'procedural') NOT NULL DEFAULT 'episodic',
    category VARCHAR(50),  -- 'preference', 'weakness', 'goal', 'fact', 'habit', 'strength'

    -- 记忆内容
    content TEXT NOT NULL,
    summary VARCHAR(255),  -- 摘要，用于快速展示

    -- 元数据
    metadata JSON,
    source VARCHAR(50) DEFAULT 'conversation',  -- 'conversation', 'behavior', 'explicit'

    -- 向量检索
    embedding_json TEXT,

    -- 记忆管理
    importance FLOAT DEFAULT 0.5,
    confidence FLOAT DEFAULT 0.8,
    access_count INT DEFAULT 0,
    last_accessed_at DATETIME,

    -- 生命周期
    expires_at DATETIME,
    is_active BOOLEAN DEFAULT TRUE,

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    INDEX idx_user_type (user_id, memory_type),
    INDEX idx_user_category (user_id, category),
    INDEX idx_importance (importance DESC),
    INDEX idx_active (is_active, user_id),
    INDEX idx_expires (expires_at),

    CONSTRAINT fk_memories_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);

-- 记忆关联表
CREATE TABLE memory_relations (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    source_memory_id BIGINT NOT NULL,
    target_memory_id BIGINT NOT NULL,
    relation_type VARCHAR(50) DEFAULT 'related',  -- 'related', 'contradicts', 'evolved_into'
    strength FLOAT DEFAULT 0.5,

    FOREIGN KEY (source_memory_id) REFERENCES ai_memories(id) ON DELETE CASCADE,
    FOREIGN KEY (target_memory_id) REFERENCES ai_memories(id) ON DELETE CASCADE,
    UNIQUE KEY uk_relation (source_memory_id, target_memory_id)
);

-- 记忆访问日志表
CREATE TABLE memory_access_logs (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    memory_id BIGINT NOT NULL,
    user_id INT NOT NULL,
    access_type VARCHAR(20),  -- 'recall', 'update', 'delete'
    query_text TEXT,
    relevance_score FLOAT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_memory (memory_id),
    INDEX idx_user_time (user_id, created_at),

    CONSTRAINT fk_memory_log_memory
        FOREIGN KEY (memory_id)
        REFERENCES ai_memories(id)
        ON DELETE CASCADE,
    CONSTRAINT fk_memory_log_user
        FOREIGN KEY (user_id)
        REFERENCES users(id)
        ON DELETE CASCADE
);
