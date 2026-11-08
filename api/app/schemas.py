# ============================================================================
# schemas.py — 请求 / 响应数据模型（Pydantic）
# 作用：对客户端传入的数据做结构与格式校验，并限制客户端能发送哪些字段。
# 关键：任何“系统字段”（role、owner、created_at 等）都不在请求模型里，
#       客户端无法伪造，满足 ЛР2「服务器自行计算系统字段」的要求。
# ============================================================================
import re

from pydantic import BaseModel, EmailStr, Field, field_validator

# 密码强度校验：至少 8 位，含大小写字母与数字
_PASSWORD_RE = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$")


# --------------------------- 认证相关请求 ---------------------------

class RegisterRequest(BaseModel):
    """注册请求。仅允许 email 和 password；角色由服务器强制为 student。"""
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def _strong_password(cls, v: str) -> str:
        # 服务器端强度校验（接口隐藏按钮只算便利，服务器校验才是保护）
        if not _PASSWORD_RE.match(v):
            raise ValueError("пароль должен содержать заглавную и строчную буквы и цифру")
        return v


class LoginRequest(BaseModel):
    """登录请求（O-07 /api/v1/auth/token）。"""
    email: EmailStr
    password: str


class ResetRequest(BaseModel):
    """找回密码：请求验证码。只要求邮箱。"""
    email: EmailStr


class ResetConfirm(BaseModel):
    """找回密码：用一次性验证码设置新密码。"""
    email: EmailStr
    code: str = Field(min_length=6, max_length=6)
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def _strong_password(cls, v: str) -> str:
        if not _PASSWORD_RE.match(v):
            raise ValueError("новый пароль слишком слабый")
        return v


# --------------------------- 认证相关响应 ---------------------------

class TokenResponse(BaseModel):
    """登录成功响应：访问令牌 + 类型 + 有效期秒数。不含任何密码信息。"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class UserOut(BaseModel):
    """对外暴露的用户信息：不含 password_hash / password_salt。"""
    id: str
    email: str
    role: str


class MessageOut(BaseModel):
    """通用消息响应（注册/找回密码等）。"""
    message: str


# ============================================================================
# 任务 4：业务端点的数据模型（按 ЛР2 第 2 节契约）
# 关键：请求模型里绝不包含 owner_id / student_id / actor_id / status 等
#       系统字段——这些一律由服务器计算，客户端无法伪造（TB-02 防提权）。
# ============================================================================

class GradeOut(BaseModel):
    """成绩对象对外字段（O-01/O-03/O-04）。
    只暴露业务需要的字段；绝不返回密码、内部主键外键以外的敏感列。"""
    id: str
    enrollment_id: str
    value: float | None
    status: str
    version: int
    updated_at: str | None = None


class GradePatchRequest(BaseModel):
    """修改成绩（O-03）。客户端只能提交新分值与乐观锁版本号；
    owner/updated_by/updated_at/status 由服务器写。"""
    value: float = Field(ge=0, le=100)
    version: int = Field(ge=1, description="客户端读到的当前版本，用于乐观锁")


class RetakeCreateRequest(BaseModel):
    """创建补考/清欠申请（O-02）。
    客户端只提交 course_id 与 reason；student_id 由服务器根据令牌决定。"""
    course_id: str
    reason: str = Field(min_length=5, max_length=2000)


class RetakeOut(BaseModel):
    """补考申请对外字段。"""
    id: str
    enrollment_id: str
    reason: str
    status: str
    created_at: str | None = None


class CourseOut(BaseModel):
    """课程对象（O-08）。"""
    id: str
    code: str
    owner_id: str


class AdminConfirmRequest(BaseModel):
    """管理员确认成绩（O-05）。action 由客户端声明（approve/reject），
    但只有 employee 角色能调用；谁操作由服务器审计。"""
    action: str = Field(pattern="^(approve|reject)$")


class AuditEventOut(BaseModel):
    """审计事件（O-09，仅管理员可见）。"""
    id: str
    actor_id: str | None
    action: str
    object_id: str | None
    time: str | None = None
