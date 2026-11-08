# ============================================================================
# seed.py — 测试数据写入（任务 2.3 / 任务 4 演示数据）
# 作用：系统启动时幂等地准备：
#   - 两个普通学生 + 一个教师 + 一个特权员工（口令均以 Argon2id+pepper 哈希入库）；
#   - 一门课程 CS-101（教师为 owner）；
#   - 两个学生都选这门课，各有一条成绩记录。
# 这样答辩时可以演示：学生 A 用自己的令牌看不到学生 B 的成绩（对象级隔离）。
# ============================================================================
import logging

from . import config, security

logger = logging.getLogger("gradebook.seed")


async def ensure_test_users(pool) -> None:
    """幂等地创建测试用户（已存在则跳过）。"""
    for u in config.SEED_USERS:
        exists = await pool.fetchval(
            "SELECT 1 FROM users WHERE email = $1", u["email"]
        )
        if exists:
            continue
        password_hash, password_salt = security.hash_password(u["password"])
        await pool.execute(
            "INSERT INTO users (email, role, password_hash, password_salt) "
            "VALUES ($1, $2, $3, $4)",
            u["email"], u["role"], password_hash, password_salt,
        )
        logger.info("创建测试用户 %s（角色 %s）", u["email"], u["role"])


async def ensure_demo_data(pool) -> None:
    """幂等地创建课程、选课与成绩演示数据。"""
    teacher_id = await pool.fetchval("SELECT id FROM users WHERE email = $1", "teacher@test.edu")
    student1_id = await pool.fetchval("SELECT id FROM users WHERE email = $1", "student@test.edu")
    student2_id = await pool.fetchval("SELECT id FROM users WHERE email = $1", "student2@test.edu")
    if not (teacher_id and student1_id and student2_id):
        return  # 用户还没就绪，跳过（下次启动再补）

    # 课程 CS-101，owner 是教师
    course_id = await pool.fetchval(
        "SELECT id FROM courses WHERE code = $1", "CS-101"
    )
    if not course_id:
        course_id = await pool.fetchval(
            "INSERT INTO courses (code, owner_id) VALUES ($1, $2) RETURNING id",
            "CS-101", teacher_id,
        )
        logger.info("创建课程 CS-101")

    # 给两个学生分别选课
    for user_id, score in ((student1_id, 85), (student2_id, 60)):
        enrollment_id = await pool.fetchval(
            "SELECT id FROM enrollments WHERE user_id = $1 AND course_id = $2",
            user_id, course_id,
        )
        if not enrollment_id:
            enrollment_id = await pool.fetchval(
                "INSERT INTO enrollments (user_id, course_id) VALUES ($1, $2) RETURNING id",
                user_id, course_id,
            )
        # 若该选课还没有成绩，则补一条
        has_grade = await pool.fetchval(
            "SELECT 1 FROM grades WHERE enrollment_id = $1", enrollment_id
        )
        if not has_grade:
            await pool.execute(
                "INSERT INTO grades (enrollment_id, value, status) VALUES ($1, $2, 'current')",
                enrollment_id, score,
            )
            logger.info("为 user=%s 写入成绩 %s", user_id, score)


async def seed_all(pool) -> None:
    """启动时依次准备用户与演示数据。"""
    await ensure_test_users(pool)
    await ensure_demo_data(pool)
