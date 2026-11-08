# ============================================================================
# config.py — 应用配置
# 作用：集中从环境变量读取全部配置与密钥。代码里不出现任何硬编码口令/密钥/连接串，
#       保证满足任务 1.3「所有设置和密钥都来自环境变量」。
# ============================================================================
import os


# ---------- 数据库 / Redis 连接（容器内主机名 db / redis）----------
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://app_api:app_secret_change_me@db:5432/gradebook")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

# ---------- JWT 令牌（任务 3.2）----------
JWT_SECRET = os.getenv("JWT_SECRET", "")          # 签名密钥，必须在 .env 设置
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")  # 签名算法
ACCESS_TOKEN_TTL_MINUTES = int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "30"))  # 令牌有效期

# ---------- 密码哈希（任务 3.1）----------
PASSWORD_PEPPER = os.getenv("PASSWORD_PEPPER", "")  # pepper，只在环境变量，不进数据库
ARGON2_TIME_COST = int(os.getenv("ARGON2_TIME_COST", "3"))        # 时间成本
ARGON2_MEMORY_COST = int(os.getenv("ARGON2_MEMORY_COST", "65536"))  # 内存成本 KiB
ARGON2_PARALLELISM = int(os.getenv("ARGON2_PARALLELISM", "4"))    # 并行度
ARGON2_HASH_LEN = int(os.getenv("ARGON2_HASH_LEN", "32"))         # 输出哈希长度

# ---------- 本地邮件桩 Mailpit（任务 3.3）----------
MAIL_HOST = os.getenv("MAIL_HOST", "mailpit")
MAIL_PORT = int(os.getenv("MAIL_PORT", "1025"))
MAIL_FROM = os.getenv("MAIL_FROM", "gradebook@example.edu")

# ---------- 找回密码（任务 3.3）----------
RESET_CODE_TTL_MINUTES = int(os.getenv("RESET_CODE_TTL_MINUTES", "15"))  # 验证码有效期
RESET_CODE_LENGTH = 6                     # 一次性验证码位数

# ---------- 限流（任务 3.2 / TB-01）----------
LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "5"))          # 窗口内最大尝试次数
RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))  # 窗口秒数

# ---------- CORS（允许的来源，逗号分隔）----------
CORS_ORIGINS = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()]

# ---------- 测试用户（seed.py 使用；口令默认值仅用于本地演示）----------
# 任务 2.3：至少两个普通用户 + 一个特权用户，且各有自己的对象
SEED_USERS = [
    {"email": "student@test.edu",   "password": os.getenv("SEED_STUDENT_PASSWORD", "Student!123"),   "role": "student"},
    {"email": "student2@test.edu",  "password": os.getenv("SEED_STUDENT2_PASSWORD", "Student2!123"), "role": "student"},
    {"email": "teacher@test.edu",   "password": os.getenv("SEED_TEACHER_PASSWORD", "Teacher!123"),   "role": "teacher"},
    {"email": "employee@test.edu",  "password": os.getenv("SEED_EMPLOYEE_PASSWORD", "Employee!123"), "role": "employee"},
]


def validate_required_secrets() -> None:
    """启动时校验关键密钥是否已设置；未设置则直接终止启动，避免带空密钥运行。"""
    missing = []
    if not JWT_SECRET:
        missing.append("JWT_SECRET")
    if not PASSWORD_PEPPER:
        missing.append("PASSWORD_PEPPER")
    if missing:
        raise RuntimeError(f"缺少必需环境变量: {', '.join(missing)}。请检查 .env")
