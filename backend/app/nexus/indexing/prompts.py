"""Versioned legal assertion extraction prompt."""
from __future__ import annotations

import json

from nexus.domain import Block

PROMPT_VERSION = "assertion-first-1"
EXTRACTOR_VERSION = "assertion-first-1"
ONTOLOGY_VERSION = "legal-assertion-1"

SYSTEM_PROMPT = """你是中国法规结构化抽取器。只输出一个 JSON 对象，不要解释。

必须使用以下完整结构：
{
  "empty": false,
  "empty_reason": null,
  "entities": [
    {"local_id":"e1","mention_text":"原文中的名称","canonical_name":"规范名称",
     "entity_type":"Reg|Org|Activity|Product|Category|Concept","aliases":[],
     "start_offset":0,"end_offset":5,"confidence":0.99}
  ],
  "actions": [
    {"local_id":"a1","canonical_text":"完整行动","verb":"核心动词",
     "participants":[{"role":"object|recipient|authority|beneficiary|instrument|target",
                      "entity_local_id":"e2","value_text":null}],"confidence":0.95}
  ],
  "assertions": [
    {"local_id":"s1","kind":"norm|definition|relation|deadline|penalty",
     "predicate":"小写英文目录词","modality":"must|must_not|may|should|factual|conditional_may",
    "action_local_id":"a1","participants":[{"role":"subject|object|recipient|authority|beneficiary|regulation|activity|product|term",
                        "entity_local_id":"e1 或 null","value_text":"实体原文或非实体化字面值"}],
     "condition":null,"exception":null,"scope":null,"payload":null,
     "quote":"连续原文","quote_start":0,"quote_end":10,"confidence":0.95}
  ]
}

严格规则：
1. quote 和 mention_text 必须是输入 block.text 中连续、逐字相同的子串。offset 尽量给出；系统会以原文精确定位结果为准。
2. 所有 entity_local_id 必须引用 entities 中已声明 local_id；所有 action_local_id 必须引用 actions。
3. norm/deadline/penalty 必须有 action；relation 的所有参与者必须引用实体。norm 的 subject 应优先引用实体；原文主体不适合建稳定实体时可 entity_local_id=null 并保留 value_text。普通 object 等角色若不是稳定实体，也可使用字面值。
4. 模态只能在原文有词汇支持时使用：must=应当/必须/须/负责/需，must_not=不得/禁止/严禁，may=可以/可，should=宜/建议/鼓励，conditional_may=在条件下可以/可。国家支持、促进、制定、提升等陈述若没有义务词，必须用 factual。
5. Entity 只能是可跨条文复用的法规、机构、活动、产品、分类、概念，不把整句义务当实体。
6. Action 的参与者只包含行动内在对象/接收方/主管方等；主体和模态属于 Assertion。
7. 没有可抽取法规断言时必须显式返回 {"empty":true,"empty_reason":"具体原因","entities":[],"actions":[],"assertions":[]}。绝不能返回空对象。
8. 不得猜测原文没有的信息；宁缺毋滥。"""


def user_prompt(block: Block, validation_feedback: list[dict] | None = None) -> str:
    payload = {
        "block": {
            "block_id": block.block_id,
            "heading_path": block.heading_path,
            "article_no": block.article_no,
            "paragraph_no": block.paragraph_no,
            "item_no": block.item_no,
            "text": block.text,
        }
    }
    if validation_feedback:
        payload["previous_validation_errors"] = validation_feedback
        payload["instruction"] = "修正全部错误后重新输出完整 JSON；不要省略字段。"
    return json.dumps(payload, ensure_ascii=False, indent=2)
