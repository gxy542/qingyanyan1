-- ============================================================================
-- roles.sql  — 应用专用数据库角色（最小权限，任务 3.5 的设计）
-- 作用：创建 app_api 角色，只授予 SELECT/INSERT/UPDATE/DELETE，不授予任何 DDL。
-- 结果：应用账号无法 DROP TABLE / CREATE TABLE —— 这在答辩时演示“最小权限”。
-- 本脚本由 initdb 以超级用户 postgres 身份执行，因此可以创建角色并授权。
-- 注意：这里写死的口令必须与 .env 中 APP_DB_PASSWORD 一致。
-- ============================================================================

DO $$
BEGIN
    -- 只在角色不存在时创建（避免镜像重启时报错）
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_api') THEN
        CREATE ROLE app_api LOGIN PASSWORD 'app_secret_change_me';
    END IF;
END $$;

-- 允许连接数据库（库名必须与 POSTGRES_DB 一致）
GRANT CONNECT ON DATABASE gradebook TO app_api;
-- 允许使用 public 模式
GRANT USAGE ON SCHEMA public TO app_api;
-- 对现有全部表授予增删改查
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_api;
-- 允许使用序列（后续若用自增主键）
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO app_api;

-- 刻意未授予：CREATE / ALTER / DROP —— 应用角色无法修改表结构（TB-03 边界控制）
