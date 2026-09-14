"""服务层异常（PRD 13.10 统一错误响应：error_code / error_message / trace_id）。

约定：服务层一律抛出本模块的异常，由接口层统一转换为标准错误响应；
禁止在业务代码里直接抛 HTTP 异常，以保证服务层不依赖具体 Web 框架。
"""

__all__ = ["ServiceError", "BadRequest", "NotFound", "Conflict", "PermissionDenied"]


class ServiceError(Exception):
    """服务层异常基类。"""

    error_code = "INTERNAL_ERROR"  # 错误码：接口层透出给调用方
    status_code = 500              # 对应的 HTTP 状态码

    def __init__(self, message: str, detail: dict | None = None) -> None:
        super().__init__(message)
        self.message = message      # 错误说明
        self.detail = detail or {}  # 附加信息（如定位到具体字段）


class BadRequest(ServiceError):
    """请求不合法：字段缺失、取值越界、格式错误（PRD 13.10）。"""

    error_code = "INVALID_REQUEST"
    status_code = 400


class NotFound(ServiceError):
    """资源不存在：单据、附件、任务或报告查不到（PRD 13.10）。"""

    error_code = "RESOURCE_NOT_FOUND"
    status_code = 404


class Conflict(ServiceError):
    """状态冲突：当前状态不允许该操作（PRD 7.3 流转表拦截）。"""

    error_code = "STATE_CONFLICT"
    status_code = 409


class PermissionDenied(ServiceError):
    """权限不足：未登录或超出数据权限范围（PRD 3.3、16）。"""

    error_code = "PERMISSION_DENIED"
    status_code = 403
