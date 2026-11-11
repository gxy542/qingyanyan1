# ============================================================================
# overview.py — 成绩册总览端点（为前端“电子日志”界面提供联表数据）
#
#   GET /api/v1/overview/gradebook  员工/教师：全部学生 × 课程的成绩网格
#   GET /api/v1/overview/my         学生：本人成绩（带课程代码）
#
# 安全要点：
#   - 员工端点 require_role("employee","teacher")，学生无法调用；
#   - 学生端点强制按当前令牌 user_id 过滤，看不到别人；
#   - 全部参数化 SQL，禁止拼接。
# ============================================================================
import logging

from fastapi import APIRouter, Depends, Request

from .. import errors, schemas
from ..deps import CurrentUser, get_current_user, require_role

logger = logging.getLogger("gradebook.overview")
router = APIRouter(prefix="/api/v1/overview", tags=["overview"])

# 可查看完整成绩册的角色
_STAFF_ROLES = ("employee", "teacher")


@router.get("/gradebook", response_model=list[schemas.GradebookRowOut])
async def staff_gradebook(request: Request,
                          user: CurrentUser = Depends(require_role(*_STAFF_ROLES))):
    """员工/教师成绩册：联表返回 学生邮箱、课程代码、成绩、状态、版本。"""
    pool = request.app.state.pool
    try:
        rows = await pool.fetch(
            """
            SELECT g.id AS grade_id, u.email AS student_email, c.code AS course_code,
                   g.value, g.status, g.version
              FROM grades g
              JOIN enrollments e ON e.id = g.enrollment_id
              JOIN users u       ON u.id = e.user_id
              JOIN courses c     ON c.id = e.course_id
             ORDER BY c.code, u.email
             LIMIT 200
            """
        )
        return [
            schemas.GradebookRowOut(
                grade_id=str(r["grade_id"]),
                student_email=r["student_email"],
                course_code=r["course_code"],
                value=float(r["value"]) if r["value"] is not None else None,
                status=r["status"],
                version=r["version"],
            )
            for r in rows
        ]
    except Exception as exc:
        raise await errors.internal_error(exc)


@router.get("/my", response_model=list[schemas.MyGradeRowOut])
async def my_grades(request: Request,
                    user: CurrentUser = Depends(get_current_user)):
    """学生本人成绩：强制按当前用户过滤，带课程代码。"""
    pool = request.app.state.pool
    try:
        rows = await pool.fetch(
            """
            SELECT g.id AS grade_id, c.code AS course_code,
                   g.value, g.status, g.version
              FROM grades g
              JOIN enrollments e ON e.id = g.enrollment_id
              JOIN courses c     ON c.id = e.course_id
             WHERE e.user_id = $1
             ORDER BY c.code
            """,
            user.id,
        )
        return [
            schemas.MyGradeRowOut(
                grade_id=str(r["grade_id"]),
                course_code=r["course_code"],
                value=float(r["value"]) if r["value"] is not None else None,
                status=r["status"],
                version=r["version"],
            )
            for r in rows
        ]
    except Exception as exc:
        raise await errors.internal_error(exc)
