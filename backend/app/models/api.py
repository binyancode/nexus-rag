"""API 层请求/响应模型（与检索引擎领域模型解耦）。"""
from typing import Any, Optional

from models.base import BaseSchema


class AskRequest(BaseSchema):
    """一次自然语言提问。"""
    q: str
    as_user: Optional[str] = None


class AskResponse(BaseSchema):
    """最终答案 + 逐条溯源。"""
    answer: str
    sources: list[Any] = []
