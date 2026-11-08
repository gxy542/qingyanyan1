# ============================================================================
# retake.py — 补考 / 清欠申请端点（任务 4，契约 O-02 / O-06）
#
#   POST /api/v1/retake-requests            O-02 学生创建补考申请
#   POST /api/v1/retake-requests/{id}/check  O-06 LLM 检查（按 ЛР3 例外返回 501）
#
# 安全要点：
#   - student_id 由服务器根据“当前用户 + course_id”反查 enrollment 得出，
#     客户端在 body 里传 owner_id/student_id/status 一律无效（模型里没有这些字段）；
#   - 同一 enrollment 同时只允许一个 pending 申请 → 409（幂等/重复提交防护）。
# ============================================================================
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import errors, schemas
from ..deps import CurrentUser, get_current_user, require_role

logger = logging.getLogger("gradebook.retake")
router = APIRouter(prefix="/api/v1/retake-requests", tags=["retake"])


@router.post("", response_model=schemas.RetakeOut, status_code=201)
async def create_retake(body: schemas.RetakeCreateRequest, request: Request,
                        user: CurrentUser = Depends(require_role("student"))):
    """O-02 创建补考申请。

    - 只有 student 能创建；
    - 服务器根据 course_id + 当前用户查 enrollment，找不到 → 400（未选该课）；
    - 已有 pending 申请 → 409（活跃申请唯一约束）；
    - reason 长度由 Pydantic 校验（5–2000）。
    """
    pool = request.app.state.pool
    try:
        # 服务器端反查选课记录（owner/student 不接受客户端传入）
        enrollment = await pool.fetchrow(
            """
            SELECT e.id FROM enrollments e
             WHERE e.user_id = $1 AND e.course_id = $2::uuid
            """,
            user.id, body.course_id,
        )
        if enrollment is None:
            raise HTTPException(status_code=400, detail="Вы не записаны на этот курс")

        enrollment_id = enrollment["id"]

        # 活跃申请唯一约束：已有 pending 申请则拒绝
        active = await pool.fetchval(
            "SELECT 1 FROM retake_requests WHERE enrollment_id = $1 AND status = 'pending'",
            enrollment_id,
        )
        if active:
            raise HTTPException(status_code=409, detail="Уже есть активная заявка на пересдачу")

        new_id = await pool.fetchval(
            "INSERT INTO retake_requests (enrollment_id, reason) VALUES ($1, $2) RETURNING id",
            enrollment_id, body.reason,
        )

        row = await pool.fetchrow(
            "SELECT id, enrollment_id, reason, status, created_at FROM retake_requests WHERE id = $1",
            new_id,
        )
        return schemas.RetakeOut(
            id=str(row["id"]),
            enrollment_id=str(row["enrollment_id"]),
            reason=row["reason"],
            status=row["status"],
            created_at=row["created_at"].isoformat() if row["created_at"] else None,
        )
    except HTTPException:
        raise
    except Exception as exc:
        # course_id 不是合法 uuid 等也走这里 → 中性 500/400
        raise await errors.internal_error(exc)


@router.post("/{request_id}/check", status_code=501)
async def check_retake(request_id: str, request: Request,
                       user: CurrentUser = Depends(get_current_user)):
    """O-06 LLM 检查补考申请。

    按 ЛР3 第 3 节例外：本工作不接入语言模型，端点保留为桩，返回 501。
    """
    raise HTTPException(status_code=501, detail="LLM-проверка не реализована в этой работе")
