# ============================================================================
# admin.py — 管理员 / 特权端点（任务 4，契约 O-05 / O-09）
#
#   POST /api/v1/admin/grades/{id}/confirm  O-05 员工确认成绩（仅 employee + 强制审计）
#   GET  /api/v1/audit/events                O-09 管理员读取审计事件
#
# 安全要点：
#   - require_role("employee") 做 RBAC 闸门，普通用户/学生调用一律 403；
#   - 确认动作无论 approve/reject 都强制写 audit_log；
#   - 已 closed 的成绩不能重复确认 → 409。
# ============================================================================
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import errors, schemas
from ..deps import CurrentUser, require_role

logger = logging.getLogger("gradebook.admin")
router = APIRouter(prefix="/api/v1", tags=["admin"])


@router.post("/admin/grades/{grade_id}/confirm", response_model=schemas.GradeOut)
async def confirm_grade(grade_id: str, body: schemas.AdminConfirmRequest,
                        request: Request,
                        user: CurrentUser = Depends(require_role("employee"))):
    """O-05 员工确认成绩。

    - approve：成绩置为 closed（最终确认）；
    - reject：保持 current，仅记录审计；
    - 每次操作强制写 audit_log；重复确认已 closed 的成绩 → 409。
    """
    pool = request.app.state.pool
    try:
        gid = uuid.UUID(grade_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Не найдено")

    try:
        row = await pool.fetchrow(
            "SELECT id, value, status, version FROM grades WHERE id = $1", gid
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Не найдено")
        if row["status"] == "closed":
            raise HTTPException(status_code=409, detail="Оценка уже подтверждена")

        if body.action == "approve":
            await pool.execute(
                """
                UPDATE grades SET status = 'closed', version = version + 1,
                                  updated_by = $1, updated_at = now()
                 WHERE id = $2
                """,
                user.id, gid,
            )

        # 强制审计：记录这次特权操作
        await pool.execute(
            "INSERT INTO audit_log (actor_id, action, object_id) VALUES ($1, $2, $3)",
            user.id, f"grade.confirm.{body.action}", gid,
        )

        updated = await pool.fetchrow(
            "SELECT id, enrollment_id, value, status, version, updated_at FROM grades WHERE id = $1",
            gid,
        )
        return schemas.GradeOut(
            id=str(updated["id"]),
            enrollment_id=str(updated["enrollment_id"]),
            value=float(updated["value"]) if updated["value"] is not None else None,
            status=updated["status"],
            version=updated["version"],
            updated_at=updated["updated_at"].isoformat() if updated["updated_at"] else None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise await errors.internal_error(exc)


@router.get("/audit/events", response_model=list[schemas.AuditEventOut])
async def list_audit_events(request: Request,
                            user: CurrentUser = Depends(require_role("employee"))):
    """O-09 审计事件列表（仅 employee）。最新 200 条。"""
    pool = request.app.state.pool
    try:
        rows = await pool.fetch(
            """
            SELECT id, actor_id, action, object_id, time
              FROM audit_log
             ORDER BY time DESC
             LIMIT 200
            """
        )
        return [
            schemas.AuditEventOut(
                id=str(r["id"]),
                actor_id=str(r["actor_id"]) if r["actor_id"] else None,
                action=r["action"],
                object_id=str(r["object_id"]) if r["object_id"] else None,
                time=r["time"].isoformat() if r["time"] else None,
            )
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as exc:
        raise await errors.internal_error(exc)
