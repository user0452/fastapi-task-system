CREATE DATABASE IF NOT EXISTS task_db2
DEFAULT CHARACTER SET utf8mb4
DEFAULT COLLATE utf8mb4_unicode_ci;

USE task_db2;

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
