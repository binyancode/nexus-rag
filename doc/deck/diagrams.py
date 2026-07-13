# -*- coding: utf-8 -*-
"""Assertion-first architecture diagrams. Every function returns a 1280×720 SVG."""
from __future__ import annotations

import math

from slides_lib import (
    svg, text, rect, line, arrow, circle, pill, wrapw, card, cap, node, codebox,
    W, H, INK, MUTE, FAINT, NAVY, BLUE, BLUE_SOFT, TEAL, TEAL_SOFT,
    GREEN, GREEN_SOFT, ORANGE, ORANGE_SOFT, PURPLE, PURPLE_SOFT,
    RED, LINE, PANEL, MONO,
)

SOFT = {
    BLUE: BLUE_SOFT, TEAL: TEAL_SOFT, GREEN: GREEN_SOFT,
    ORANGE: ORANGE_SOFT, PURPLE: PURPLE_SOFT, RED: "#F9E2DF", NAVY: "#E3EBF4",
}
MARKER = {BLUE: "arrow", TEAL: "arrowt", GREEN: "arrowg", ORANGE: "arrowo", PURPLE: "arrowp", MUTE: "arrowm"}


def ml(x, y, value, width_chars=28, size=13, color=MUTE, weight="500", lh=None,
       max_lines=5, anchor="start", ff=None):
    """Wrapped SVG text with a deterministic line budget."""
    lines = wrapw(str(value), width_chars)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip("…") + "…"
    lh = lh or size * 1.45
    out = []
    for i, value_line in enumerate(lines):
        out.append(text(x, y + i * lh, value_line, size, color, weight, anchor=anchor,
                        ff=ff or "'Microsoft YaHei','Segoe UI',sans-serif"))
    return "".join(out)


def arrowc(x1, y1, x2, y2, color=BLUE, sw=2.2, dash=None):
    return arrow(x1, y1, x2, y2, color, sw, dash=dash, marker=MARKER.get(color, "arrow"))


def badge(x, y, label, color, width=None):
    width = width or max(62, len(label) * 15 + 24)
    return pill(x, y, width, 26, SOFT.get(color, BLUE_SOFT), label, 11.5, color, "800")


def titleline(value):
    return cap(value, y=156, size=15)


def small_card(x, y, w, h, title, body, color, number=None, body_chars=28):
    o = [card(x, y, w, h, accent=color)]
    tx = x + 22
    if number:
        o.append(circle(x + 30, y + 30, 15, fill=color))
        o.append(text(x + 30, y + 35, number, 12, "#FFFFFF", "800", anchor="middle"))
        tx = x + 56
    o.append(text(tx, y + 32, title, 15, INK, "800"))
    o.append(ml(x + 22, y + 62, body, body_chars, 12.2, MUTE, "600", max_lines=4))
    return "".join(o)


def flow_box(x, y, w, h, title, sub, color, tag=None):
    o = [card(x, y, w, h, accent=color, shadow=False)]
    o.append(text(x + 20, y + 31, title, 13.2 if tag else 14, INK, "800"))
    if tag:
        tag_width = max(46, len(tag) * 8 + 16)
        o.append(pill(x + w - tag_width - 12, y + 13, tag_width, 26,
                      SOFT.get(color, BLUE_SOFT), tag, 10.5, color, "800"))
    o.append(ml(x + 20, y + 57, sub, max(12, int((w - 34) / 11)), 11.5, MUTE, "600", max_lines=3))
    return "".join(o)


def cover():
    o = [rect(0, 0, W, H, "url(#cover)")]
    # right-side truth model constellation
    cx, cy = 1005, 347
    rings = [(166, "Block", BLUE), (116, "Assertion", PURPLE), (66, "Graph", GREEN)]
    for radius, label, color in rings:
        o.append(circle(cx, cy, radius, fill="none", stroke="#FFFFFF", sw=1.2, opacity=.14))
        o.append(circle(cx + radius * .70, cy - radius * .70, 9, fill=color, opacity=.9))
        o.append(text(cx + radius * .70 + 15, cy - radius * .70 + 5, label, 12, "#D9EBFB", "700"))
    for angle in (20, 95, 165, 235, 305):
        rad = math.radians(angle)
        px, py = cx + math.cos(rad) * 125, cy + math.sin(rad) * 125
        o.append(line(cx, cy, px, py, "#8FD3FF", 1.3, opacity=.33))
        o.append(circle(px, py, 7, fill="#8FD3FF", opacity=.65))
    o.append(circle(cx, cy, 34, fill="#FFFFFF"))
    o.append(text(cx, cy + 6, "事实", 15, NAVY, "800", anchor="middle"))

    o.append(rect(88, 142, 56, 6, TEAL))
    o.append(text(88, 212, "法规检索系统设计", 45, "#FFFFFF", "800"))
    o.append(text(90, 263, "Assertion-first · Generation 原子发布 · 强类型 SQG / 确定性 PEP",
                  18.5, "#CFE6FB", "500"))
    o.append(pill(90, 300, 338, 42, "#1C82D6", "可见 · 可溯源 · 可发布 · 可回滚", 15, "#FFFFFF", "700"))
    o.append(line(90, 444, 725, 444, "#3E6C99", 1))
    o.append(text(90, 484, "索引：原文 → 法规断言 → 稳定词汇 → 派生图", 16, "#B9D5EE", "600"))
    o.append(text(90, 516, "查询：自然语言 → SQG → 确定性 PEP → 事实与原文依据", 16, "#B9D5EE", "600"))
    o.append(text(90, 664, "2026-07   ·   Assertion-first 重建设计", 14, "#8FB2D6", "500"))
    return svg("".join(o), bg="#0B2C4E")


def overview():
    o = [titleline("端到端一张图：索引构建可信事实，查询编译可见计划；Graph 只负责导航，不替代原文事实。")]
    # index lane
    o.append(rect(64, 184, 1152, 128, "#F5F8FC", rx=14, stroke="#D9E5F1", sw=1.2))
    o.append(badge(82, 199, "① 索引 · 离线", BLUE, 108))
    idx = [
        ("法规原文", "条 / 款 / 项", BLUE),
        ("结构化切块", "稳定 Block ID", BLUE),
        ("抽取断言", "主体 · 行动 · 模态", PURPLE),
        ("归一词汇", "Entity · Action", TEAL),
        ("质量门禁", "检查后再发布", ORANGE),
        ("Active Generation", "一次切换", GREEN),
    ]
    xs = [82, 266, 450, 634, 818, 1002]
    for i, (t, s, c) in enumerate(idx):
        o.append(flow_box(xs[i], 236, 150, 58, t, s, c))
        if i < len(idx) - 1:
            o.append(arrowc(xs[i] + 151, 265, xs[i + 1] - 3, 265, MUTE, 1.7))
    # truth model
    o.append(rect(64, 330, 1152, 128, "#F8F5FC", rx=14, stroke="#E4DDF1", sw=1.2))
    o.append(badge(82, 345, "② 事实模型", PURPLE, 96))
    truth = [
        ("Block", "原文与向量", BLUE),
        ("Assertion", "法规事实真值", PURPLE),
        ("Entity", "稳定概念", TEAL),
        ("Action", "可比较行动", ORANGE),
        ("Graph Edge", "由断言派生", GREEN),
    ]
    xs2 = [112, 328, 544, 760, 976]
    for i, (t, s, c) in enumerate(truth):
        o.append(node(xs2[i], 374, 146, 56, t, SOFT[c], c, sub=s, tsize=13.5))
        if i < len(truth) - 1:
            o.append(arrowc(xs2[i] + 148, 402, xs2[i + 1] - 4, 402, MUTE, 1.8))
    # query lane
    o.append(rect(64, 476, 1152, 150, "#F4FAF7", rx=14, stroke="#D7EBDD", sw=1.2))
    o.append(badge(82, 491, "③ 查询 · 在线", GREEN, 108))
    qry = [
        ("初始化器", "冻结 Collection", GREEN),
        ("SQG 编译器", "只表达查什么", PURPLE),
        ("PEP 规划器", "固定模板", ORANGE),
        ("Workflow", "执行物理算子", TEAL),
        ("答案生成器", "事实 + 原文", GREEN),
    ]
    xs3 = [82, 306, 530, 754, 978]
    for i, (t, s, c) in enumerate(qry):
        o.append(flow_box(xs3[i], 530, 174, 72, t, s, c))
        if i < len(qry) - 1:
            o.append(arrowc(xs3[i] + 176, 566, xs3[i + 1] - 3, 566, MUTE, 1.8))
    return svg("".join(o))


def principles():
    o = [titleline("六条原则决定系统边界：事实与导航分开、构建与发布分开、意图与执行分开。")]
    items = [
        ("Assertion 是事实", "法规结论必须同时保存主体、行动、模态、条件、例外和适用范围。", PURPLE),
        ("Block 是证据", "每条事实必须回到连续原文 Quote；答案引用 Assertion + Block。", BLUE),
        ("Graph 是导航", "图边由事实派生，用于关联和集合计算，不作为最终真值。", GREEN),
        ("Generation 隔离", "构建中的数据不可查；质量通过后一次切换，失败不污染线上。", ORANGE),
        ("SQG / PEP 分层", "LLM 只理解业务意图；确定性规划器生成物理执行图。", TEAL),
        ("Collection 是边界", "一次查询冻结 Store 与 Active Generation，所有读取都不能越界。", NAVY),
    ]
    for i, item in enumerate(items):
        col, row = i % 3, i // 3
        o.append(small_card(70 + col * 387, 188 + row * 184, 366, 160,
                            item[0], item[1], item[2], f"{i + 1:02d}", 24))
    o.append(rect(70, 566, 1140, 72, "#0E2E52", rx=13))
    o.append(text(92, 594, "设计结果", 13, "#8FD3FF", "800"))
    o.append(text(92, 620, "任何答案都能回答三件事：结论是什么、由哪条事实支持、原文在哪里。",
                  15, "#EAF3FF", "700"))
    return svg("".join(o))


def truth_model():
    o = [titleline("事实链不是一条粗边，而是一组可核对对象：原文、断言、参与者、行动，再派生导航关系。")]
    # left source block
    o.append(card(70, 188, 340, 402, accent=BLUE))
    o.append(text(94, 220, "Block · 原文证据", 16, BLUE, "800"))
    quote = "疾病预防控制机构应当按照规定\n向接种单位供应疫苗。"
    o.append(rect(94, 246, 292, 92, "#EEF5FC", rx=10, stroke="#C9DDF1", sw=1))
    o.append(ml(112, 276, quote, 25, 14, NAVY, "700", lh=25, max_lines=3))
    o.append(badge(94, 356, "article-35", BLUE, 92))
    o.append(text(94, 400, "稳定地址", 11, MUTE, "700"))
    o.append(text(94, 423, "doc:article-35", 12, NAVY, "700", ff=MONO))
    o.append(text(94, 462, "Primary Quote", 11, MUTE, "700"))
    o.append(text(94, 485, "start / end 精确定位", 12, NAVY, "700", ff=MONO))
    o.append(text(94, 548, "原文与向量存 AI Search", 11.5, MUTE, "600"))
    # center assertion
    o.append(card(462, 188, 340, 402, accent=PURPLE))
    o.append(text(486, 220, "Legal Assertion · 事实", 16, PURPLE, "800"))
    rows = [
        ("主体", "疾病预防控制机构", TEAL),
        ("模态", "must · 应当", RED),
        ("行动", "向接种单位供应疫苗", ORANGE),
        ("条件", "按照规定", BLUE),
        ("例外", "无", MUTE),
    ]
    for i, (k, v, c) in enumerate(rows):
        yy = 252 + i * 55
        o.append(badge(486, yy, k, c, 58))
        o.append(text(560, yy + 18, v, 13, INK, "700"))
    o.append(line(486, 540, 778, 540, LINE, 1))
    o.append(text(486, 564, "assertion_id  +  confidence  +  state", 11.5, MUTE, "600", ff=MONO))
    # right words and graph
    o.append(card(854, 188, 356, 402, accent=GREEN))
    o.append(text(878, 220, "稳定词汇 + 派生 Graph", 16, GREEN, "800"))
    o.append(node(886, 276, 140, 54, "Org · 疾控机构", TEAL_SOFT, TEAL, tsize=12.5))
    o.append(node(1046, 276, 140, 54, "Action · 供应疫苗", ORANGE_SOFT, ORANGE, tsize=12.5))
    o.append(arrowc(1028, 303, 1042, 303, GREEN, 2.2))
    o.append(text(1035, 266, "has_obligation", 9.5, GREEN, "700", anchor="middle"))
    o.append(rect(886, 338, 300, 94, "#F4FAF6", rx=10, stroke="#CDE8D7", sw=1))
    o.append(text(906, 366, "graph_edge_support", 12.5, GREEN, "800", ff=MONO))
    o.append(text(906, 391, "edge → assertion_id", 12, INK, "700", ff=MONO))
    o.append(text(906, 415, "导航关系可回到事实", 11.5, MUTE, "600"))
    o.append(rect(886, 456, 300, 94, "#FFF7EF", rx=10, stroke="#F0D4B7", sw=1))
    o.append(text(906, 484, "关键边界", 12.5, ORANGE, "800"))
    o.append(ml(906, 509, "Graph 可加速关联与集合计算，但不能替代 Assertion 和原文。", 24, 11.5, MUTE, "600", max_lines=2))
    o.append(arrowc(412, 390, 456, 390, BLUE, 2.5))
    o.append(arrowc(804, 390, 848, 390, PURPLE, 2.5))
    return svg("".join(o))


def assertion_anatomy():
    o = [titleline("一条 Assertion 把法律语义拆开保存：模态与条件不再被压成一个模糊的 requires 关系。")]
    # source sentence
    o.append(rect(70, 184, 1140, 74, "#0E2E52", rx=12))
    o.append(text(92, 211, "原文", 12, "#8FD3FF", "800"))
    o.append(text(92, 239, "应对重大突发公共卫生事件急需的疫苗，经评估获益大于风险的，可以附条件批准疫苗注册申请。",
                  16, "#FFFFFF", "700"))
    # anatomy cards
    fields = [
        ("kind", "norm", "规范性事实", PURPLE),
        ("subject", "药品监管部门", "谁承担 / 决定", TEAL),
        ("modality", "conditional_may", "符合条件时可以", RED),
        ("action", "附条件批准注册申请", "可比较的完整行动", ORANGE),
        ("condition", "急需 + 获益大于风险", "结论成立前提", BLUE),
        ("evidence", "quote + span", "连续原文证据", GREEN),
    ]
    for i, (k, v, d, c) in enumerate(fields):
        col, row = i % 3, i // 3
        x, y = 70 + col * 387, 286 + row * 140
        o.append(card(x, y, 366, 118, accent=c))
        o.append(text(x + 22, y + 29, k, 12, c, "800", ff=MONO))
        o.append(text(x + 22, y + 57, v, 14, INK, "800"))
        o.append(text(x + 22, y + 85, d, 11.5, MUTE, "600"))
    o.append(rect(70, 582, 1140, 62, "#F7F9FC", rx=12, stroke=LINE, sw=1))
    o.append(text(94, 608, "查询收益", 13, NAVY, "800"))
    o.append(text(208, 608, "可区分“应当 / 不得 / 可以”，可筛选条件，可比较主体职责，可逐条引用原文。", 13, MUTE, "700"))
    return svg("".join(o))


def schema_map():
    o = [titleline("SQL 保存结构与运行状态，AI Search 保存原文和向量；所有数据都以 Generation 隔离。")]
    groups = [
        ("配置与作用域", ["search_store", "collection", "collection_store", "collection_access"], BLUE, 70),
        ("发布与文档", ["index_generation", "document", "document_version", "block_manifest"], GREEN, 355),
        ("事实模型", ["entity / alias / mention", "action / participant / mention", "legal_assertion", "assertion_entity / evidence"], PURPLE, 640),
        ("派生与运行", ["graph_edge / support", "index_run / node / quality", "query_run / stage / node"], ORANGE, 925),
    ]
    for title, rows, c, x in groups:
        o.append(card(x, 188, 265, 330, accent=c))
        o.append(text(x + 22, 222, title, 15, INK, "800"))
        yy = 252
        for row in rows:
            o.append(rect(x + 22, yy, 221, 46, SOFT[c], rx=8, stroke=c, sw=.8))
            o.append(ml(x + 36, yy + 28, row, 24, 11.5, c, "800", lh=15, max_lines=2, ff=MONO))
            yy += 62
    # AI Search band
    o.append(rect(70, 548, 1140, 94, "#0E2E52", rx=13))
    o.append(text(94, 579, "Azure AI Search", 15, "#FFFFFF", "800"))
    o.append(text(94, 608, "Block 原文 · Vector · generation_id · document_id · 条/款/项结构字段", 13, "#BFD7EC", "600"))
    o.append(badge(982, 575, "只查冻结代次", GREEN, 190))
    return svg("".join(o))


def generation():
    o = [titleline("用户按文档新增或替换；系统继承未变文档组成完整候选代次，通过门禁后才切换 Active Generation。")]
    # active lane
    o.append(card(70, 188, 500, 350, accent=GREEN))
    o.append(text(94, 221, "线上可查询", 15, GREEN, "800"))
    o.append(node(116, 258, 170, 64, "Generation A", GREEN_SOFT, GREEN, sub="active"))
    o.append(flow_box(330, 258, 192, 64, "查询流量", "Collection 快照始终指向 A", GREEN))
    o.append(arrowc(288, 290, 326, 290, GREEN, 2.4))
    o.append(rect(104, 358, 432, 132, "#F3FAF6", rx=11, stroke="#D3E8D9", sw=1))
    o.append(text(128, 389, "失败也不影响线上", 14, INK, "800"))
    o.append(ml(128, 417, "构建中的 Block、Assertion 和 Graph 不可见；当前查询快照仍然稳定。", 34, 12, MUTE, "600", max_lines=3))
    # build lane
    o.append(card(642, 188, 568, 350, accent=ORANGE))
    o.append(text(666, 221, "后台构建", 15, ORANGE, "800"))
    stages = [("building", BLUE), ("validating", ORANGE), ("active", GREEN)]
    xs = [674, 856, 1038]
    for i, (s, c) in enumerate(stages):
        o.append(node(xs[i], 258, 140, 58, s, SOFT[c], c, tsize=13))
        if i < 2:
            o.append(arrowc(xs[i] + 142, 287, xs[i + 1] - 4, 287, MUTE, 2))
    o.append(rect(674, 350, 492, 138, "#FFF8F1", rx=11, stroke="#F0D5BB", sw=1))
    o.append(text(698, 380, "继承与原子激活", 14, INK, "800"))
    tx = ["B.base_generation_id → A", "未上传文档从 A 继承", "比较 A 后切换 Active → B"]
    for i, row in enumerate(tx):
        o.append(circle(704, 408 + i * 24, 3, fill=ORANGE))
        o.append(text(716, 413 + i * 24, row, 12, MUTE, "700", ff=MONO))
    # bottom rollback
    o.append(rect(70, 566, 1140, 72, "#F7F9FC", rx=12, stroke=LINE, sw=1))
    o.append(text(94, 594, "可恢复", 13, NAVY, "800"))
    o.append(text(180, 594, "历史 Query Run 保存 generation_scope；Retired Generation 可保留、回滚或延迟清理。", 13, MUTE, "700"))
    return svg("".join(o))


def index_workflow():
    o = [titleline("索引是一张可观测 DAG：先继承未变文档，只重建新增/替换文档，最后发布完整候选代次。")]
    # split
    o.append(flow_box(36, 264, 130, 78, "继承文档", "事实 + 原文 + 向量", NAVY))
    o.append(arrowc(168, 303, 198, 303, NAVY, 2.2))
    o.append(flow_box(202, 264, 130, 78, "文档切块", "仅新增 / 替换文档", BLUE))
    o.append(arrowc(334, 303, 374, 230, BLUE, 2.3))
    o.append(arrowc(334, 303, 374, 394, BLUE, 2.3))
    o.append(flow_box(378, 188, 150, 84, "逐块抽取", "LLM → Assertion", PURPLE))
    o.append(flow_box(378, 354, 150, 84, "向量化写入", "Embedding → Search", GREEN))
    o.append(arrowc(530, 230, 572, 303, PURPLE, 2.3))
    o.append(arrowc(530, 396, 572, 303, GREEN, 2.3))
    o.append(flow_box(576, 264, 160, 78, "精确归一", "新旧事实统一去重", TEAL))
    o.append(arrowc(738, 303, 770, 303, TEAL, 2.3))
    o.append(flow_box(774, 264, 140, 78, "重建 Graph", "完整事实 → Edge", GREEN))
    o.append(arrowc(916, 303, 948, 303, GREEN, 2.3))
    o.append(flow_box(952, 264, 140, 78, "质量门禁", "完整性 + 范围", ORANGE))
    o.append(arrowc(1094, 303, 1128, 303, ORANGE, 2.3))
    o.append(node(1132, 272, 104, 62, "原子发布", GREEN_SOFT, GREEN, tsize=12))
    # detail row
    details = [
        ("抽取并行", "每个 Block 一个节点；原始输出、错误和 Token 全部留痕。", PURPLE, 70),
        ("归一集中", "规范名优先、别名回退；Action 用完整参与者签名比较。", TEAL, 355),
        ("失败传播", "关键节点失败，下游自动跳过；取消不会触碰线上代次。", RED, 640),
        ("发布隔离", "构建期间查询仍指向旧 Active Generation。", GREEN, 925),
    ]
    for t, d, c, x in details:
        o.append(small_card(x, 480, 265, 130, t, d, c, body_chars=21))
    return svg("".join(o))


def extraction_guardrails():
    o = [titleline("LLM 输出不直接入库：先修复可确定问题，再逐条校验；坏项隔离，整体异常才阻止发布。")]
    steps = [
        ("Attempt 1", "严格 JSON + Quote + Participant 校验", PURPLE),
        ("反馈重试", "把具体错误交给模型完整修正", BLUE),
        ("本地修复", "Offset、空白、角色别名、枚举证据包络", TEAL),
        ("逐条隔离", "保留有效 Assertion，错误项留审计", ORANGE),
        ("质量门禁", "隔离块 ≤ 5% 可发布；超限拒绝", RED),
    ]
    xs = [70, 302, 534, 766, 998]
    for i, (t, d, c) in enumerate(steps):
        o.append(flow_box(xs[i], 210, 188, 110, t, d, c, f"{i + 1}"))
        if i < 4:
            o.append(arrowc(xs[i] + 190, 264, xs[i + 1] - 4, 264, MUTE, 2))
    # policy comparison
    o.append(card(70, 370, 550, 222, accent=GREEN))
    o.append(text(94, 402, "可自动修复 / 隔离", 15, GREEN, "800"))
    good = ["模型 Offset 计数偏移", "前置句 + 枚举项的非连续 Quote", "Payload 类型漂移", "单条 Action / Assertion 结构错误"]
    for i, row in enumerate(good):
        o.append(text(100, 438 + i * 34, "✓", 14, GREEN, "800"))
        o.append(text(124, 438 + i * 34, row, 12.5, MUTE, "700"))
    o.append(card(660, 370, 550, 222, accent=RED))
    o.append(text(684, 402, "仍然硬失败", 15, RED, "800"))
    bad = ["Quote 无法在原文定位", "未知 Entity / Action 引用", "没有任何可用 Assertion", "隔离块超过 5%"]
    for i, row in enumerate(bad):
        o.append(text(690, 438 + i * 34, "×", 14, RED, "800"))
        o.append(text(714, 438 + i * 34, row, 12.5, MUTE, "700"))
    return svg("".join(o))


def normalization():
    o = [titleline("归一目标是高精度、可解释：规范名精确命中优先，别名只在无规范名命中时使用。")]
    o.append(card(70, 188, 540, 386, accent=TEAL))
    o.append(text(94, 220, "Entity 归一", 16, TEAL, "800"))
    # pipeline
    boxes = [
        ("同类型 + 规范名", "唯一命中 → matched", GREEN),
        ("否则查别名", "唯一命中 → matched", BLUE),
        ("多候选", "ambiguous → 门禁", ORANGE),
        ("无候选", "新建 candidate", PURPLE),
    ]
    for i, (t, s, c) in enumerate(boxes):
        yy = 252 + i * 70
        o.append(flow_box(98, yy, 466, 54, t, s, c))
        if i < len(boxes) - 1:
            o.append(arrowc(330, yy + 55, 330, yy + 69, MUTE, 1.8))
    o.append(rect(98, 530, 466, 28, "#F7F9FC", rx=7))
    o.append(text(114, 549, "例：规范名“主要负责人”优先于“关键岗位人员”的宽泛别名。", 10.8, MUTE, "600"))

    o.append(card(650, 188, 560, 386, accent=ORANGE))
    o.append(text(674, 220, "Action 归一", 16, ORANGE, "800"))
    o.append(codebox(678, 248, 504, 172, [
        ("verb: 供应", "#93D07E"),
        ("object: 疫苗", "#CFE0F0"),
        ("recipient: 接种单位", "#CFE0F0"),
        ("qualifier: 按照规定", "#E0B072"),
        ("signature_hash: sha256(结构)", "#9FB4C8"),
    ], title="完整行动签名", accent=ORANGE, fs=12.5, lh=22))
    o.append(rect(678, 444, 504, 96, "#FFF7EF", rx=10, stroke="#F0D5BB", sw=1))
    o.append(text(700, 473, "不再把“备案 / 报告 / 符合条件”单独全局合并", 12.5, ORANGE, "800"))
    o.append(ml(700, 502, "Action 必须带对象、接收方等上下文，才能用于主体之间的交集与差集。", 39, 11.5, MUTE, "600", max_lines=2))
    return svg("".join(o))


def quality_gate():
    o = [titleline("质量门禁不是附加测试，而是发布事务的前置条件：硬错误为零，有限隔离可带警告发布。")]
    metrics = [
        ("Block 抽取完成", "pending / failed = 0", GREEN),
        ("AI Search 写入完整", "Manifest 数 = 搜索索引数", BLUE),
        ("参与者已解析", "Accepted Assertion 无悬空引用", TEAL),
        ("原文证据完整", "每条事实有 1 个 Primary Quote", PURPLE),
        ("Graph 支持完整", "每条边至少 1 个 Assertion", ORANGE),
        ("隔离比例受控", "≤ max(1, 5% Block)", RED),
    ]
    for i, (t, d, c) in enumerate(metrics):
        col, row = i % 3, i // 3
        x, y = 70 + col * 387, 190 + row * 142
        o.append(small_card(x, y, 366, 118, t, d, c, f"{i + 1}", body_chars=27))
    # gate outcome
    o.append(rect(70, 506, 1140, 132, "#0E2E52", rx=14))
    o.append(text(94, 540, "门禁结果", 15, "#8FD3FF", "800"))
    outcomes = [("PASS", "原子切换 Active Generation", GREEN), ("WARN", "记录隔离块，仍可发布", ORANGE), ("FAIL", "保留旧代次，新代次不可见", RED)]
    for i, (t, d, c) in enumerate(outcomes):
        x = 94 + i * 360
        o.append(badge(x, 558, t, c, 72))
        o.append(text(x + 88, 577, d, 12.5, "#DCEBFA", "700"))
    return svg("".join(o))


def query_stages():
    o = [titleline("在线查询固定五阶段：每阶段有明确输入输出、状态、Token 和错误，页面可逐级查看。")]
    stages = [
        ("初始化器", "QueryContext", "冻结 Collection / Generation", GREEN),
        ("SQG 编译器", "SQG", "强类型业务意图", PURPLE),
        ("PEP 规划器", "PEP", "确定性物理计划", ORANGE),
        ("Workflow 协调器", "Facts + Evidence", "执行固定算子", TEAL),
        ("答案生成器", "Answer + Citations", "只消费显式输入", GREEN),
    ]
    xs = [55, 304, 553, 802, 1051]
    for i, (t, out, d, c) in enumerate(stages):
        o.append(flow_box(xs[i], 214, 180, 112, t, d, c, str(i + 1)))
        o.append(badge(xs[i] + 20, 342, out, c, 140))
        if i < len(stages) - 1:
            o.append(arrowc(xs[i] + 182, 270, xs[i + 1] - 4, 270, MUTE, 2.2))
    # boundaries
    blocks = [
        ("LLM", "只在 SQG 与最终回答使用", PURPLE, 70),
        ("确定性", "PEP 规划、集合运算、范围校验", TEAL, 355),
        ("安全范围", "所有算子共享冻结 Generation Scope", BLUE, 640),
        ("可追溯", "Facts 与 Evidence 由 PEP 顶层显式绑定", GREEN, 925),
    ]
    for t, d, c, x in blocks:
        o.append(small_card(x, 454, 265, 136, t, d, c, body_chars=21))
    return svg("".join(o))


def sqg_intents():
    o = [titleline("SQG 只表达“查什么”：一个强类型 Intent，所有命名对象必须唯一绑定当前可见词汇。")]
    intents = [
        ("find_subject_facts", "查主体的 Assertion / Action", BLUE),
        ("compare_subjects", "多主体交 / 差 / 并", ORANGE),
        ("find_action_subjects", "从行动反查主体", TEAL),
        ("traverse_relation", "沿明确派生关系导航", GREEN),
        ("compare_documents", "比较明确命名文档", PURPLE),
        ("semantic_evidence", "开放语义原文检索", NAVY),
    ]
    for i, (t, d, c) in enumerate(intents):
        col, row = i % 2, i // 2
        x, y = 70 + col * 575, 190 + row * 120
        o.append(card(x, y, 550, 98, accent=c))
        o.append(text(x + 22, y + 31, t, 13, c, "800", ff=MONO))
        o.append(text(x + 22, y + 62, d, 13.5, INK, "700"))
        o.append(text(x + 510, y + 57, "›", 23, c, "800", anchor="middle"))
    o.append(rect(70, 570, 1140, 70, "#0E2E52", rx=12))
    o.append(text(94, 598, "SQG 禁止出现", 12.5, "#8FD3FF", "800"))
    o.append(text(216, 598, "SQL · Store · Generation · Vector · TopK · 物理算子 · 图方向 / 跳数", 13, "#EAF3FF", "700", ff=MONO))
    o.append(text(94, 623, "逻辑意图与物理执行彻底分离。", 11.5, "#A9C4DE", "600"))
    return svg("".join(o))


def pep_templates():
    o = [titleline("PEP 不由 LLM 自由生成：规划器绑定稳定 ID 后，选择经过评审的固定模板。")]
    # template 1
    o.append(card(70, 188, 1140, 130, accent=ORANGE))
    o.append(text(94, 218, "模板 A · 多主体职责差集", 15, ORANGE, "800"))
    names = [("EntityLookup A", BLUE), ("SubjectActions A", TEAL), ("Diff", ORANGE), ("GroundAssertions", PURPLE)]
    xs = [100, 320, 615, 930]
    for i, (t, c) in enumerate(names):
        o.append(node(xs[i], 246, 174, 48, t, SOFT[c], c, tsize=12.3))
        if i < len(names) - 1:
            o.append(arrowc(xs[i] + 176, 270, xs[i + 1] - 4, 270, MUTE, 1.8))
    o.append(node(320, 300, 174, 0, "", PANEL, PANEL)) if False else None
    o.append(text(514, 290, "＋ 独立 B 分支", 10.5, MUTE, "700"))
    # template 2
    o.append(card(70, 336, 550, 230, accent=PURPLE))
    o.append(text(94, 368, "模板 B · 文档比较", 15, PURPLE, "800"))
    o.append(node(98, 402, 148, 50, "BlockSearch 文档1", BLUE_SOFT, BLUE, tsize=11.5))
    o.append(node(98, 474, 148, 50, "BlockSearch 文档2", BLUE_SOFT, BLUE, tsize=11.5))
    o.append(node(370, 438, 180, 54, "EvidenceBundle", PURPLE_SOFT, PURPLE, tsize=12.5))
    o.append(arrowc(248, 427, 366, 461, BLUE, 2))
    o.append(arrowc(248, 499, 366, 461, BLUE, 2))
    # template 3
    o.append(card(660, 336, 550, 230, accent=TEAL))
    o.append(text(684, 368, "模板 C · 开放证据", 15, TEAL, "800"))
    o.append(node(704, 418, 174, 58, "BlockSearch", TEAL_SOFT, TEAL, sub="keyword / vector / hybrid", tsize=13))
    o.append(arrowc(880, 447, 930, 447, TEAL, 2.2))
    o.append(node(934, 418, 220, 58, "evidence_set", GREEN_SOFT, GREEN, sub="冻结代次内", tsize=13))
    o.append(text(684, 520, "所有模板顶层都显式绑定 outputs.facts / outputs.evidence", 11.5, MUTE, "700", ff=MONO))
    o.append(rect(70, 594, 1140, 50, "#F7F9FC", rx=10, stroke=LINE, sw=1))
    o.append(text(94, 625, "收益：同一个 SQG 稳定生成同一个 PEP；错误可复现，类型可校验，行为不随模型随机漂移。", 12.5, NAVY, "700"))
    return svg("".join(o))


def operators():
    o = [titleline("物理算子按职责分组：绑定、事实读取、图导航、集合计算、取证与原文检索。")]
    groups = [
        ("绑定", ["EntityLookup", "ActionLookup"], BLUE),
        ("事实", ["SubjectAssertions", "SubjectActions", "ActionSubjects", "AssertionSearch"], PURPLE),
        ("图导航", ["GraphTraverse"], GREEN),
        ("集合", ["FilterModality", "Intersect", "Diff", "Union"], ORANGE),
        ("取证", ["GroundAssertions"], TEAL),
        ("原文", ["BlockSearch", "EvidenceBundle"], NAVY),
    ]
    for i, (title, rows, c) in enumerate(groups):
        col, row = i % 3, i // 3
        x, y = 70 + col * 387, 188 + row * 190
        o.append(card(x, y, 366, 166, accent=c))
        o.append(text(x + 22, y + 32, title, 15, c, "800"))
        yy = y + 60
        for op in rows:
            o.append(rect(x + 22, yy, 322, 24, "#F7F9FC", rx=6))
            o.append(text(x + 34, yy + 17, op, 11.5, INK, "700", ff=MONO))
            yy += 29
    o.append(rect(70, 590, 1140, 52, "#0E2E52", rx=10))
    o.append(text(94, 622, "GroundAssertions 只返回结果事实自己的 Quote，不拿实体的其他出处替代关系证据。", 12.5, "#EAF3FF", "700"))
    return svg("".join(o))


def collection_scope():
    o = [titleline("Collection 决定能查什么；Initializer 再冻结每个 Store 的 Active Generation，形成不可变安全快照。")]
    # collection left
    o.append(card(70, 188, 330, 382, accent=BLUE))
    o.append(text(94, 220, "Collection · 查询范围", 16, BLUE, "800"))
    o.append(node(110, 258, 250, 58, "法规库 Collection", BLUE_SOFT, BLUE, sub="当前用户可见", tsize=13.5))
    stores = [("Store A", "gen-101"), ("Store B", "gen-208")]
    for i, (s, g) in enumerate(stores):
        yy = 350 + i * 92
        o.append(node(110, yy, 112, 50, s, TEAL_SOFT, TEAL, tsize=12))
        o.append(node(248, yy, 112, 50, g, GREEN_SOFT, GREEN, tsize=12))
        o.append(arrowc(224, yy + 25, 244, yy + 25, TEAL, 1.8))
    o.append(text(110, 540, "一个 Store 没有 Active Generation → 初始化失败", 10.5, RED, "700"))
    # snapshot center
    o.append(codebox(442, 210, 380, 326, [
        ('"collection_id": "regulations"', "#CFE0F0"),
        ('"allowed_stores": ["A","B"]', "#93D07E"),
        ('"generation_scope": {', "#E0B072"),
        ('  "A": "gen-101",', "#CFE0F0"),
        ('  "B": "gen-208"', "#CFE0F0"),
        ('}', "#E0B072"),
        ('"budgets": { ... }', "#9FB4C8"),
    ], title="Frozen QueryContext", accent=PURPLE, fs=13, lh=29))
    # enforcement right
    o.append(card(864, 188, 346, 382, accent=GREEN))
    o.append(text(888, 220, "所有读取都执行同一边界", 15, GREEN, "800"))
    rules = [
        ("SQL", "每个查询从 Store / Generation CTE 开始"),
        ("AI Search", "每次调用必须显式过滤 generation_id"),
        ("Graph", "只走冻结代次的 edge + support"),
        ("Document", "先绑定冻结文档，再下推 document_id"),
        ("PEP", "只能缩小范围，不能换 Store / Generation"),
    ]
    for i, (t, d) in enumerate(rules):
        yy = 250 + i * 60
        o.append(badge(888, yy, t, GREEN if i else BLUE, 82))
        o.append(ml(982, yy + 17, d, 22, 11.3, MUTE, "700", lh=16, max_lines=2))
    o.append(rect(70, 596, 1140, 48, "#F7F9FC", rx=10, stroke=LINE, sw=1))
    o.append(text(94, 626, "历史 Query Run 保存 generation_scope，因此即使后来发布新代次，旧运行仍可解释。", 12.5, NAVY, "700"))
    return svg("".join(o))


def graph_role():
    o = [titleline("Graph 用于快速导航和集合计算；点击任何边都能回到支持它的 Assertion 和原文 Quote。")]
    # mini graph
    o.append(card(70, 188, 680, 390, accent=GREEN))
    o.append(text(94, 220, "派生导航图", 16, GREEN, "800"))
    nodes = [
        ("药品审评中心", 118, 282, TEAL),
        ("负责申请审评", 356, 240, ORANGE),
        ("优先审评审批", 356, 380, ORANGE),
        ("药监局", 592, 310, TEAL),
    ]
    for label, x, y, c in nodes:
        o.append(node(x, y, 134, 56, label, SOFT[c], c, tsize=12))
    o.append(arrowc(254, 310, 352, 268, GREEN, 2.4))
    o.append(arrowc(254, 310, 352, 408, GREEN, 2.4))
    o.append(arrowc(490, 268, 588, 338, GREEN, 2.4))
    o.append(text(303, 271, "has_obligation", 10, GREEN, "700", anchor="middle"))
    o.append(text(303, 379, "has_action", 10, GREEN, "700", anchor="middle"))
    o.append(text(538, 284, "regulated_by", 10, GREEN, "700", anchor="middle"))
    o.append(rect(108, 478, 604, 66, "#F4FAF6", rx=10, stroke="#D4E9DC", sw=1))
    o.append(text(132, 505, "Graph Edge", 11.5, GREEN, "800", ff=MONO))
    o.append(text(132, 529, "→ graph_edge_support → assertion_id → quote / block", 12, NAVY, "700", ff=MONO))
    # boundary right
    o.append(card(790, 188, 420, 390, accent=PURPLE))
    o.append(text(814, 220, "Graph 适合 / 不适合", 16, PURPLE, "800"))
    o.append(text(820, 260, "适合", 13, GREEN, "800"))
    good = ["按明确关系向前 / 反向导航", "查共同行动与职责差异", "快速加载邻域和支持数量"]
    for i, row in enumerate(good):
        o.append(text(824, 291 + i * 34, "✓", 13.5, GREEN, "800"))
        o.append(text(848, 291 + i * 34, row, 12, MUTE, "700"))
    o.append(line(814, 390, 1186, 390, LINE, 1))
    o.append(text(820, 422, "不适合", 13, RED, "800"))
    bad = ["用边替代完整法规事实", "用实体其他出处证明当前关系", "把图中不存在解释成法律绝对不存在"]
    for i, row in enumerate(bad):
        o.append(text(824, 453 + i * 34, "×", 13.5, RED, "800"))
        o.append(text(848, 453 + i * 34, row, 12, MUTE, "700"))
    return svg("".join(o))


def example_diff():
    o = [titleline("示例：查“药品审评中心承担、但国家药品监督管理局不直接承担的职责”，Graph 与集合算子协同完成。")]
    # question
    o.append(rect(70, 184, 1140, 56, "#0E2E52", rx=11))
    o.append(text(94, 219, "问题：药品审评中心承担、但国家药品监督管理局不直接承担的职责有哪些？", 14.5, "#FFFFFF", "700"))
    # branches
    o.append(node(100, 290, 170, 54, "EntityLookup", BLUE_SOFT, BLUE, sub="药品审评中心", tsize=12.5))
    o.append(node(100, 420, 170, 54, "EntityLookup", BLUE_SOFT, BLUE, sub="国家药监局", tsize=12.5))
    o.append(node(334, 290, 184, 54, "SubjectActions", TEAL_SOFT, TEAL, sub="职责集合 A", tsize=12.5))
    o.append(node(334, 420, 184, 54, "SubjectActions", TEAL_SOFT, TEAL, sub="职责集合 B", tsize=12.5))
    o.append(node(610, 355, 150, 58, "Diff", ORANGE_SOFT, ORANGE, sub="A − B", tsize=14))
    o.append(node(846, 355, 190, 58, "GroundAssertions", PURPLE_SOFT, PURPLE, sub="只取幸存事实原文", tsize=12.5))
    o.append(arrowc(272, 317, 330, 317, BLUE, 2.2))
    o.append(arrowc(272, 447, 330, 447, BLUE, 2.2))
    o.append(arrowc(520, 317, 606, 380, TEAL, 2.2))
    o.append(arrowc(520, 447, 606, 380, TEAL, 2.2))
    o.append(arrowc(762, 384, 842, 384, ORANGE, 2.2))
    # result
    o.append(card(1066, 278, 144, 214, accent=GREEN))
    o.append(text(1086, 310, "结果", 14, GREEN, "800"))
    o.append(text(1086, 344, "1 项", 25, NAVY, "800"))
    o.append(ml(1086, 378, "负责临床试验申请、上市许可申请、补充申请等审评", 11, 11.5, MUTE, "700", lh=18, max_lines=5))
    o.append(badge(1084, 452, "第 5 条", GREEN, 92))
    # note
    o.append(rect(70, 540, 1140, 94, "#FFF8F1", rx=12, stroke="#F0D5BB", sw=1))
    o.append(text(94, 570, "边界说明", 13, ORANGE, "800"))
    o.append(ml(198, 570, "差集表示“当前冻结 Collection 中未出现在右侧职责集合”，不能扩展成普遍意义上的绝对不承担。", 74, 12.5, MUTE, "700", max_lines=2))
    return svg("".join(o))


def example_documents():
    o = [titleline("示例：明确比较两份法规时，不走实体集合；各自检索原文后用 EvidenceBundle 保留证据分组。")]
    o.append(card(70, 188, 1140, 352, accent=PURPLE))
    o.append(text(94, 220, "两份文档 · 两条独立证据分支", 15, PURPLE, "800"))
    # branches
    o.append(node(112, 272, 190, 58, "BlockSearch", BLUE_SOFT, BLUE, sub="文档 A · doc_id=A", tsize=13))
    o.append(node(112, 400, 190, 58, "BlockSearch", BLUE_SOFT, BLUE, sub="文档 B · doc_id=B", tsize=13))
    o.append(node(470, 336, 210, 62, "EvidenceBundle", PURPLE_SOFT, PURPLE, sub="保留 A / B 分组", tsize=14))
    o.append(node(834, 336, 230, 62, "Answer Generator", GREEN_SOFT, GREEN, sub="先分别说明，再比较", tsize=13.5))
    o.append(arrowc(304, 301, 466, 367, BLUE, 2.4))
    o.append(arrowc(304, 429, 466, 367, BLUE, 2.4))
    o.append(arrowc(682, 367, 830, 367, PURPLE, 2.4))
    o.append(rect(1092, 286, 92, 54, BLUE_SOFT, rx=9, stroke=BLUE, sw=1))
    o.append(text(1138, 308, "A 引用", 11, BLUE, "800", anchor="middle"))
    o.append(text(1138, 328, "只证 A", 10.5, MUTE, "700", anchor="middle"))
    o.append(rect(1092, 394, 92, 54, TEAL_SOFT, rx=9, stroke=TEAL, sw=1))
    o.append(text(1138, 416, "B 引用", 11, TEAL, "800", anchor="middle"))
    o.append(text(1138, 436, "只证 B", 10.5, MUTE, "700", anchor="middle"))
    # rules bottom
    rules = [
        ("真实 doc_id", "文档名先绑定当前冻结代次", BLUE),
        ("组间隔离", "不能用 A 的证据证明 B", PURPLE),
        ("公平预算", "两组都必须进入生成器", ORANGE),
        ("空组处理", "任一文档无证据则明确不足", RED),
    ]
    for i, (t, d, c) in enumerate(rules):
        o.append(small_card(70 + i * 285, 568, 265, 76, t, d, c, body_chars=20))
    return svg("".join(o))


def observability():
    o = [titleline("索引与查询都保存完整运行轨迹：结构、状态、输入输出、Token、耗时、错误和原始非法输出。")]
    # left index
    o.append(card(70, 188, 540, 384, accent=BLUE))
    o.append(text(94, 220, "索引运行", 16, BLUE, "800"))
    o.append(node(110, 258, 170, 54, "index_run", BLUE_SOFT, BLUE, sub="Generation + DAG", tsize=13))
    o.append(node(344, 258, 190, 54, "index_node", TEAL_SOFT, TEAL, sub="每个 Workflow 节点", tsize=13))
    o.append(arrowc(282, 285, 340, 285, BLUE, 2))
    idx = ["抽取 Attempt 原始输出", "质量指标与隔离块", "Token / cost / error", "关闭页面后仍可恢复"]
    for i, row in enumerate(idx):
        yy = 348 + i * 45
        o.append(badge(110, yy, str(i + 1), BLUE, 34))
        o.append(text(158, yy + 18, row, 12, MUTE, "700"))
    # right query
    o.append(card(650, 188, 560, 384, accent=PURPLE))
    o.append(text(674, 220, "查询运行", 16, PURPLE, "800"))
    stages = [("run", "总体"), ("stage", "五阶段"), ("node", "PEP 节点")]
    xs = [688, 858, 1028]
    for i, (t, s) in enumerate(stages):
        o.append(node(xs[i], 258, 138, 54, t, PURPLE_SOFT, PURPLE, sub=s, tsize=13))
        if i < 2:
            o.append(arrowc(xs[i] + 140, 285, xs[i + 1] - 4, 285, PURPLE, 2))
    qry = ["QueryContext / SQG / PEP", "事实与依据显式输出", "节点状态与运行高亮", "Raw invalid 输出用于排查"]
    for i, row in enumerate(qry):
        yy = 348 + i * 45
        o.append(badge(690, yy, str(i + 1), PURPLE, 34))
        o.append(text(738, yy + 18, row, 12, MUTE, "700"))
    o.append(rect(70, 600, 1140, 44, "#0E2E52", rx=9))
    o.append(text(94, 628, "目标：从“答案不对”直接定位到哪一阶段、哪一个算子、哪一条事实或哪一段原文。", 12.5, "#EAF3FF", "700"))
    return svg("".join(o))


def module_boundaries():
    o = [titleline("实现按业务边界拆成四个 Nexus 包；通用 Workflow 独立复用，不包含法规检索语义。")]
    modules = [
        ("nexus/domain", "契约", "Assertion · Store / Collection\nQueryContext · SQG / PEP 类型", PURPLE),
        ("nexus/infrastructure", "适配", "SQL · AI Search · Chat / Embedding\nStore / Query / Graph Repository", BLUE),
        ("nexus/indexing", "构建", "Generation 索引 DAG\n抽取 · 归一 · 派生 · 门禁 · 激活", ORANGE),
        ("nexus/querying", "查询", "五阶段查询\nSQG · PEP · Operators · Recorder", TEAL),
    ]
    xs = [70, 355, 640, 925]
    for i, (name, tag, body, c) in enumerate(modules):
        x = xs[i]
        o.append(card(x, 194, 265, 258, accent=c))
        o.append(badge(x + 22, 218, tag, c, 68))
        o.append(text(x + 22, 277, name, 14, c, "800", ff=MONO))
        o.append(line(x + 22, 296, x + 243, 296, LINE, 1))
        o.append(ml(x + 22, 329, body, 22, 12, MUTE, "700", lh=24, max_lines=5))
    o.append(rect(188, 510, 904, 82, "#0E2E52", rx=13))
    o.append(text(214, 541, "app/services/workflow", 14, "#8FD3FF", "800", ff=MONO))
    o.append(text(214, 568, "通用 DAG 执行：并行 · 依赖失败传播 · 取消 · 节点耗时与 Token · Recorder 抽象", 12.5, "#EAF3FF", "700"))
    for x in xs[2:]:
        o.append(arrowc(x + 132, 508, x + 132, 456, NAVY, 1.8))
    o.append(rect(70, 618, 1140, 26, "#F7F9FC", rx=7))
    o.append(text(94, 636, "旧 models / stores / index / query / llm / core 实现已删除，避免两套模型并存。", 11.3, MUTE, "700"))
    return svg("".join(o))


def closing():
    o = [titleline("新版架构把正确性放在索引事实模型里，把稳定性放在确定性规划里，把安全性放在 Generation Scope 里。")]
    values = [
        ("事实可核对", "Assertion 保存完整法律语义，Quote 直接回到条文。", PURPLE),
        ("索引可发布", "Generation 隔离构建，质量通过后原子切换。", GREEN),
        ("查询可预测", "强类型 SQG + 固定 PEP 模板，不让模型自由造执行图。", ORANGE),
        ("范围可证明", "Collection 冻结 Store 与 Generation，所有读取统一校验。", BLUE),
        ("图可利用", "Graph 支持导航、反查、交集和差集，边有事实支持。", TEAL),
        ("过程可排查", "Run / Stage / Node 全量记录，失败位置一眼可见。", NAVY),
    ]
    for i, (t, d, c) in enumerate(values):
        col, row = i % 3, i // 3
        o.append(small_card(70 + col * 387, 190 + row * 160, 366, 136, t, d, c, body_chars=26))
    o.append(rect(70, 544, 1140, 98, "#0E2E52", rx=14))
    o.append(text(94, 578, "最终定位", 14, "#8FD3FF", "800"))
    o.append(text(94, 610, "Block 提供证据 · Assertion 提供事实 · Entity/Action 提供稳定词汇 · Graph 提供导航 · SQG/PEP 提供可见执行。",
                  14, "#FFFFFF", "700"))
    return svg("".join(o))
