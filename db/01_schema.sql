-- ============================================================================
-- schema.sql  — 数据库结构，来自 ЛР №2 的 DDL（表 3.1）
-- 该文件由 PostgreSQL 镜像的初始化目录自动执行（docker-entrypoint-initdb.d）。
-- 作用：创建系统全部数据表，并加上主键、唯一约束、外键、CHECK 约束和索引。
-- 注意：应用连接数据库时使用的是 app_api 角色（见 roles.sql），它没有建表权限，
--       因此结构只能由本脚本（以超级用户 postgres 身份）创建一次。
-- ============================================================================

-- pgcrypto 提供 gen_random_uuid()，用于生成 UUID 主键
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------------------------------------------
-- users —— 用户账号（任务三核心表）
-- email        登录名（唯一）
-- role         角色：student / teacher / employee（由服务器写入，客户端不能自选）
-- password_hash  Argon2id 哈希后的密码（含 salt 的编码串）
-- password_salt 该用户特有的随机盐（十六进制），用于验证时复现哈希
-- created_at   服务器生成，客户端不可伪造
-- ----------------------------------------------------------------------------
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         TEXT NOT NULL UNIQUE,
    role          TEXT NOT NULL CHECK (role IN ('student','teacher','employee')),
    password_hash TEXT NOT NULL,
    password_salt TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ----------------------------------------------------------------------------
-- 以下表来自 ЛР №2 数据模型，为后续任务（成绩、选课、重考、审计）预留结构。
-- ----------------------------------------------------------------------------
CREATE TABLE courses (
    id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code     TEXT NOT NULL UNIQUE,
    owner_id UUID REFERENCES users(id)
);

CREATE TABLE enrollments (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id   UUID NOT NULL REFERENCES users(id),
    course_id UUID NOT NULL REFERENCES courses(id)
);

-- grades —— 成绩（ЛР2 DDL：值域 0..100，状态机 current/retake/closed，乐观锁 version）
CREATE TABLE grades (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES enrollments(id),
    value         NUMERIC(4,2) CHECK (value BETWEEN 0 AND 100),
    status        TEXT NOT NULL CHECK (status IN ('current','retake','closed')),
    version       INTEGER NOT NULL DEFAULT 1,
    updated_by    UUID REFERENCES users(id),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- retake_requests —— 重考/补考申请（ЛР2 DDL：理由长度 5..2000，状态机）
CREATE TABLE retake_requests (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    enrollment_id UUID NOT NULL REFERENCES enrollments(id),
    reason        TEXT NOT NULL CHECK (length(reason) BETWEEN 5 AND 2000),
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','approved','rejected','completed')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- audit_log —— 审计日志（谁、何时、对哪个对象做了什么）
CREATE TABLE audit_log (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    actor_id  UUID REFERENCES users(id),
    action    TEXT NOT NULL,
    object_id UUID,
    time      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 性能与约束辅助索引
CREATE INDEX idx_grades_enrollment ON grades(enrollment_id);
CREATE INDEX idx_retake_status ON retake_requests(status);
