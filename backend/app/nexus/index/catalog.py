"""抽取目录：给 LLM 的实体类型 / 边类型结构（§1.2 / §1.4）。

不是硬编码业务改写，而是给模型足够的结构让它直接输出正确的类型/关系。
"""
from __future__ import annotations

# 实体类型（type → 说明）
ENTITY_TYPES: dict[str, str] = {
    "AppType": "申报或研究类型，如 IND、NDA、IIT、临床试验、注册申请",
    "Reg": "法规/规章/规范性文件，如《药品管理法》《药品注册管理办法》、GCP",
    "Org": "机构或监管主体，如 NMPA、药审中心、伦理委员会、申办者",
    "Requirement": "具体要求/义务/条件，如提交材料、审批时限、备案义务",
    "Category": "业务类别或主题域，如 药品、疫苗、人类遗传资源",
    "Concept": "术语或概念，如 知情同意、不良反应、受试者",
}

# 结构边类型（type → 说明）；supersedes 一期可选
EDGE_TYPES: dict[str, str] = {
    "requires": "源要求/承担/依赖目标（如申报类型→要求，机构→其承担的 Requirement）",
    "belongs_to": "源属于/隶属目标（分类归属，如某法规属于某类别）",
    "references": "源引用/参见目标（条文之间的引用）",
    "supersedes": "源取代/废止目标（新法替代旧法）",
}


def entity_types_prompt() -> str:
    return "\n".join(f"- {k}：{v}" for k, v in ENTITY_TYPES.items())


def edge_types_prompt() -> str:
    return "\n".join(f"- {k}：{v}" for k, v in EDGE_TYPES.items())
