"""统一 HTTP 异常，便于路由层直接 raise。"""

from fastapi import HTTPException, status


def unauthorized(detail: str = "无法验证身份，请重新登录") -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def bad_request(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


def not_found(detail: str = "资源不存在") -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def conflict(detail: str) -> HTTPException:
    """资源状态冲突，如文档正在向量化中不可删除。"""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)
