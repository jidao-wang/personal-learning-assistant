class AppError(Exception):
    """面向用户的可理解错误。"""


class ConfigurationError(AppError):
    """配置错误。"""


class NotFoundError(AppError):
    """资源不存在。"""


class ValidationError(AppError):
    """输入校验失败。"""
