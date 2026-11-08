# ============================================================================
# grades.py — 成绩相关端点（任务 4，契约 O-01 / O-03 / O-04）
#
#   GET   /api/v1/grades/{id}   O-01 按 ID 查成绩（对象级权限：学生只看自己）
#   PATCH /api/v1/grades/{id}   O-03 修改成绩（教师/员工 + 乐观锁 + 审计）
#   GET   /api/v1/grades         O-04 成绩列表（按 course_id 过滤，权限决定范围）
#
# 安全要点（TB-02 对象级授权 / TB-03 参数化查询）：
#   - 学生访问别人的成绩一律返回 404（不泄露对象是否存在）；
#   - 改分只有 teacher/employee；改分必须带 version，版本不符 → 409；
#   - 所有写操作都写 audit_log；
#   - 全部走 asyncpg 参数化查询，禁止拼接 SQL。
# ============================================================================
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import errors, schemas
from ..deps import CurrentUser, get_current_user, require_role

logger = logging.getLogger("gradebook.grades")
router = APIRouter(prefix="/api/v1/grades", tags=["grades"])


# 学生角色只能读自己的成绩；teacher/employee 可读全部
_TEACHER_ROLES = ("teacher", "employee")


async def _load_grade_row(pool, grade_id: uuid.UUID):
    """联表取出成绩 + 选课 + 课程，用于对象级权限判断。不存在返回 None。"""
    return await pool.fetchrow(
        """
        SELECT g.id, g.enrollment_id, g.value, g.status, g.version, g.updated_at,
               e.user_id AS student_id, c.owner_id AS course_owner_id
        FROM grades g
        JOIN enrollments e ON e.id = g.enrollment_id
        JOIN courses c     ON c.id = e.course_id
        WHERE g.id = $1
        """,
        grade_id,
    )


@router.get("/{grade_id}", response_model=schemas.GradeOut)
async def get_grade(grade_id: str, request: Request,
                    user: CurrentUser = Depends(get_current_user)):
    """O-01 按 ID 查成绩。

    - student：只能看到属于自己的成绩；看到别人的 → 404；
    - teacher/employee：可看任意成绩。
    """
    pool = request.app.state.pool
    try:
        gid = uuid.UUID(grade_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Не найдено")

    try:
        row = await _load_grade_row(pool, gid)
        if row is None:
            raise HTTPException(status_code=404, detail="Не найдено")

        # 对象级授权：学生只能访问自己的记录
        if user.role == "student" and row["student_id"] != user.id:
            # 不泄露“这条记录存在”，统一 404
            raise HTTPException(status_code=404, detail="Не найдено")

        return schemas.GradeOut(
            id=str(row["id"]),
            enrollment_id=str(row["enrollment_id"]),
            value=float(row["value"]) if row["value"] is not None else None,
            status=row["status"],
            version=row["version"],
            updated_at=row["updated_at"].isoformat() if row["updated_at"] else None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise await errors.internal_error(exc)


@router.patch("/{grade_id}", response_model=schemas.GradeOut)
async def patch_grade(grade_id: str, body: schemas.GradePatchRequest,
                      request: Request,
                      user: CurrentUser = Depends(require_role(*_TEACHER_ROLES))):
    """O-03 修改成绩（教师/员工）。

    - 乐观锁：客户端必须提交当前 version；数据库按 (id, version) 条件更新，
      影响 0 行说明版本已被别人改过 → 409。
    - 改分后 version+1、updated_by=当前用户、写审计。
    """
    pool = request.app.state.pool
    try:
        gid = uuid.UUID(grade_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Не найдено")

    try:
        # 先确认记录存在
        exists = await pool.fetchval("SELECT 1 FROM grades WHERE id = $1", gid)
        if not exists:
            raise HTTPException(status_code=404, detail="Не найдено")

        # 条件更新：version 必须等于客户端提交的值（乐观锁）
        updated = await pool.fetchrow(
            """
            UPDATE grades
               SET value = $1, version = version + 1,
                   updated_by = $2, updated_at = now()
             WHERE id = $3 AND version = $4
            RETURNING id, enrollment_id, value, status, version, updated_at
            """,
            body.value, user.id, gid, body.version,
        )
        if updated is None:
            # 版本冲突：并发修改
            raise HTTPException(status_code=409, detail="Конфликт версий. Обновите данные")

        # 写审计日志（谁、对哪个对象、做了什么）
        await pool.execute(
            "INSERT INTO audit_log (actor_id, action, object_id) VALUES ($1, $2, $3)",
            user.id, "grade.updated", gid,
        )

        return schemas.GradeOut(
            id=str(updated["id"]),
            enrollment_id=str(updated["enrollment_id"]),
            value=float(updated["value"]),
            status=updated["status"],
            version=updated["version"],
            updated_at=updated["updated_at"].isoformat() if updated["updated_at"] else None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise await errors.internal_error(exc)


@router.get("", response_model=list[schemas.GradeOut])
async def list_grades(request: Request, course_id: str | None = None,
                      user: CurrentUser = Depends(get_current_user)):
    """O-04 成绩列表。

    - 学生：只返回自己在该课程（或全部课程）的成绩；
    - teacher/employee：返回该课程（或全部）的成绩。
    """
    pool = request.app.state.pool
    try:
        clauses = []
        params: list = []
        # 学生强制加上“只能看自己”的过滤
        if user.role == "student":
            params.append(user.id)
            clauses.append("e.user_id = $" + str(len(params)))
        if course_id:
            params.append(course_id)
            clauses.append("e.course_id = $" + str(len(params)))

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = await pool.fetch(
            f"""
            SELECT g.id, g.enrollment_id, g.value, g.status, g.version, g.updated_at
              FROM grades g
              JOIN enrollments e ON e.id = g.enrollment_id
              {where}
             ORDER BY g.updated_at DESC
             LIMIT 200
            """,
            *params,
        )
        return [
            schemas.GradeOut(
                id=str(r["id"]),
                enrollment_id=str(r["enrollment_id"]),
                value=float(r["value"]) if r["value"] is not None else None,
                status=r["status"],
                version=r["version"],
                updated_at=r["updated_at"].isoformat() if r["updated_at"] else None,
            )
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as exc:
        raise await errors.internal_error(exc)
