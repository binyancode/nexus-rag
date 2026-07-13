"""实体节点（§1.2）。唯一去重的概念，entity_id = 类型:规范名。"""
from __future__ import annotations

from pydantic import BaseModel, Field


class Entity(BaseModel):
    entity_id: str                              # 如 Reg:药品管理法 / AppType:IND
    type: str                                   # AppType | Reg | Category ...
    name: str                                   # 规范名
    status: str | None = None                   # 现行 / 废止 ...
    aliases: list[str] = Field(default_factory=list)
    attrs: dict | None = None                   # 扩展属性（JSON）
    source: str = "llm"                         # seed | manual | llm（§1.5）
    locked: bool = False                        # 手工关联不被系统覆盖

    @staticmethod
    def make_id(type_: str, name: str) -> str:
        """由类型 + 规范名拼出稳定的 entity_id。"""
        return f"{type_}:{name}"
