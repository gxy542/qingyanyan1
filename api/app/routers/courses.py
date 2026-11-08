# ============================================================================
# courses.py — 课程对象端点（任务 4，契约 O-08）
#
#   GET /api/v1/courses/{id}   获取课程基本信息（任意已登录用户）
# ============================================================================
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from .. import errors, schemas
from ..deps import CurrentUser, get_current_user

logger = logging.getLogger("gradebook.courses")
router = APIRouter(prefix="/api/v1/courses", tags=["courses"])


@router.get("", response_model=list[schemas.CourseOut])
async def list_courses(request: Request,
                       user: CurrentUser = Depends(get_current_user)):
    """O-08 扩展：列出全部课程（任意已登录用户可读，供前端下拉选择）。"""
    pool = request.app.state.pool
    try:
        rows = await pool.fetch("SELECT id, code, owner_id FROM courses ORDER BY code")
        return [
            schemas.CourseOut(id=str(r["id"]), code=r["code"], owner_id=str(r["owner_id"]))
            for r in rows
        ]
    except HTTPException:
        raise
    except Exception as exc:
        raise await errors.internal_error(exc)


@router.get("/{course_id}", response_model=schemas.CourseOut)
async def get_course(course_id: str, request: Request,
                     user: CurrentUser = Depends(get_current_user)):
    """O-08 获取课程。已登录用户均可查看课程基本信息。"""
    pool = request.app.state.pool
    try:
        cid = uuid.UUID(course_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Не найдено")

    try:
        row = await pool.fetchrow(
            "SELECT id, code, owner_id FROM courses WHERE id = $1", cid
        )
        if row is None:
            raise HTTPException(status_code=404, detail="Не найдено")
        return schemas.CourseOut(
            id=str(row["id"]),
            code=row["code"],
            owner_id=str(row["owner_id"]),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise await errors.internal_error(exc)
