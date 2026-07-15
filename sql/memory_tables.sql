-- AI 长期记忆测试表结构
-- 仅包含记忆功能所需的表

USE a3_memory_test;

-- 用户表（简化版，用于测试）
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50) NOT NULL UNIQUE,
    password VARCHAR(255) NOT NULL
);

-- AI 长期记忆表
CREATE TABLE IF NOT EXISTS ai_memories (
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
CREATE TABLE IF NOT EXISTS memory_relations (
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
CREATE TABLE IF NOT EXISTS memory_access_logs (
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

-- 插入测试用户
INSERT INTO users (username, password) VALUES ('test_user', '$2b$12$LJ3m4ys3Lz0YBMOuPQslOeJKNgNGQUHYJGQK3O5JL1XJ3kQ1q2W3e');
