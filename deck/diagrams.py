# -*- coding: utf-8 -*-
"""Diagram (image) slides for 法规检索系统设计. Each returns a full 1280x720 SVG.
Native titles/footers are drawn by make_deck; here we draw body content (y~150..660)."""
from slides_lib import (svg, text, rect, line, arrow, circle, pill, wrapw, card, cap,
                        node, codebox, W, H, INK, MUTE, FAINT, NAVY, BLUE, BLUE_SOFT,
                        TEAL, TEAL_SOFT, GREEN, GREEN_SOFT, ORANGE, ORANGE_SOFT,
                        PURPLE, PURPLE_SOFT, RED, LINE, PANEL, MONO, CK, CS, CC, CN, CT, CI, CP)


def store_cyl(x, y, w, h, label, sub, color, soft, tlabel=INK, tsub=MUTE):
    cx, cy = x + 28, y + 30
    o = f'<g filter="url(#sh)">{rect(x, y, w, h, soft, rx=12, stroke=color, sw=1.5)}</g>'
    o += rect(x, y, 6, h, color, rx=3)
    o += rect(cx - 10, cy - 9, 20, 18, color)
    o += f'<ellipse cx="{cx}" cy="{cy + 9}" rx="10" ry="3.8" fill="{color}"/>'
    o += f'<ellipse cx="{cx}" cy="{cy - 9}" rx="10" ry="3.8" fill="#FFFFFF" opacity="0.6"/>'
    o += text(x + 54, y + 28, label, 15.5, tlabel, "800")
    o += text(x + 54, y + 50, sub, 12, tsub, "500")
    return o


def vcirc(cx, cy, r, color, op=0.20):
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{color}" '
            f'fill-opacity="{op}" stroke="{color}" stroke-width="2.2"/>')


def rlist_card(x, y, w, h, title, regs, accent, cols=1):
    o = card(x, y, w, h, accent=accent)
    o += text(x + 26, y + 34, title, 15.5, INK, "800")
    o += line(x + 24, y + 48, x + w - 24, y + 48, LINE, 1)
    n = len(regs)
    per = (n + cols - 1) // cols
    for i, r in enumerate(regs):
        c = i // per
        rr = i % per
        cx = x + 26 + c * (w - 40) / cols
        yy = y + 74 + rr * 27
        o += text(cx, yy, "✓", 13.5, GREEN, "800")
        o += text(cx + 20, yy, r, 13.5, INK, "600")
    return o


# ============================================================ COVER
def cover():
    import math
    o = [rect(0, 0, W, H, "url(#cover)")]
    cx, cy = 1015, 360
    for r in (150, 105, 60):
        o.append(circle(cx, cy, r, fill="none", stroke="#ffffff", sw=1, opacity=0.12))
    for i in range(6):
        a = math.radians(i * 60 - 20)
        px, py = cx + 118 * math.cos(a), cy + 118 * math.sin(a)
        o.append(line(cx, cy, px, py, "#8FD3FF", 1, opacity=0.35))
        o.append(circle(px, py, 8, fill="#8FD3FF", opacity=0.55))
    o.append(circle(cx, cy, 30, fill="#FFFFFF", opacity=0.95))
    o.append(text(cx, cy + 6, "SQG", 15, BLUE, "800", anchor="middle"))
    o.append(rect(90, 150, 54, 6, "#39B0C9"))
    o.append(text(90, 214, "法规检索系统设计", 46, "#FFFFFF", "800"))
    o.append(text(92, 264, "两层图 · 大模型编译可见的算子图(SQG) · 优化器 / 执行器", 19, "#CFE6FB", "500"))
    o.append(pill(92, 300, 300, 42, "#1C82D6", "技术设计文档 · 可见 / 可溯源 / 可排查", 15, "#FFFFFF", "700"))
    o.append(line(92, 452, 720, 452, "#3E6C99", 1))
    o.append(text(92, 490, "索引阶段：把文档变成两层图（实体层 + 块层）", 16, "#AFCDEA", "500"))
    o.append(text(92, 518, "查询阶段：大模型编译查询步骤 → 优化器 → 在两层图上执行", 16, "#AFCDEA", "500"))
    o.append(text(92, 664, "日期：2026-07   ·   版本 v0.2", 15, "#8FB2D6", "500"))
    return svg("".join(o), bg="#0B2C4E")


# ============================================================ OVERVIEW (hero)
def overview():
    o = [cap("整体一张图：索引阶段把文档建成两层图并落入三个存储；查询阶段由大模型编译算子图，经优化器在存储上执行。")]
    # ---- left: 索引阶段 ----
    o.append(rect(70, 186, 300, 452, "#F2F7FD", rx=14, stroke="#CFE0F2", sw=1.2))
    o.append(text(90, 214, "① 索引阶段（离线构建）", 15, BLUE, "800"))
    # 模块分组：输入预处理 / 图构建 / 向量化
    o.append(rect(84, 226, 272, 138, "#E8F2FD", rx=10, stroke="#C9DCF2", sw=1))
    o.append(text(98, 246, "模块A 输入预处理", 11.5, BLUE, "700"))
    o.append(rect(84, 374, 272, 138, "#EAF8F7", rx=10, stroke="#C8E8E4", sw=1))
    o.append(text(98, 394, "模块B 图构建", 11.5, TEAL, "700"))
    o.append(rect(84, 522, 272, 72, "#ECF8F1", rx=10, stroke="#CCE8DB", sw=1))
    o.append(text(98, 542, "模块C 向量化入库", 11.5, GREEN, "700"))
    steps = ["原始法规文本", "语义切块 · 赋 fullname", "抽实体并归一（实体层）",
             "LLM 建边（关系）", "块向量化"]
    for i, s in enumerate(steps):
        y = 232 + i * 74
        o.append(card(90, y, 260, 56, accent=BLUE, shadow=False))
        o.append(text(110, y + 34, s, 14.5, INK, "700"))
        if i < len(steps) - 1:
            o.append(arrow(120, y + 54, 120, y + 76, BLUE, 2.4))
    # ---- center: 三存储 ----
    o.append(rect(420, 240, 300, 344, "#E9F1FB", rx=14, stroke="#BFD2E8", sw=1.2))
    o.append(rect(420, 240, 300, 40, "#2C5D8D", rx=14))
    o.append(rect(420, 266, 300, 18, "#2C5D8D"))
    o.append(text(440, 266, "共享存储（两层图落地于此）", 13.5, "#EAF4FF", "800"))
    o.append(store_cyl(440, 286, 260, 76, "实体索引", "概念节点 名称/别名/属性", BLUE, BLUE_SOFT))
    o.append(store_cyl(440, 372, 260, 76, "边表 / 图", "requires·evidence·supersedes…", TEAL, TEAL_SOFT))
    o.append(store_cyl(440, 458, 260, 100, "块向量 + 原文", "向量索引 · text · fullname", GREEN, GREEN_SOFT))
    # 写入：索引阶段的具体步骤 -> 对应存储
    o.append(text(396, 280, "写入路径", 11.5, MUTE, "700", anchor="middle"))
    o.append('<path d="M352,408 C382,382 400,344 434,324" stroke="#1470C4" stroke-width="2" stroke-dasharray="4 3" fill="none" marker-end="url(#arrow)" stroke-linecap="round"/>')
    o.append(text(374, 356, "抽实体归一", 10.5, BLUE, "700", anchor="middle"))
    o.append('<path d="M352,482 C382,462 400,430 434,410" stroke="#0E9C9C" stroke-width="2" stroke-dasharray="4 3" fill="none" marker-end="url(#arrowt)" stroke-linecap="round"/>')
    o.append(text(376, 434, "LLM建边", 10.5, TEAL, "700", anchor="middle"))
    o.append('<path d="M352,556 C382,546 400,522 434,508" stroke="#2E9E6B" stroke-width="2" stroke-dasharray="4 3" fill="none" marker-end="url(#arrowg)" stroke-linecap="round"/>')
    o.append(text(378, 520, "块向量化", 10.5, GREEN, "700", anchor="middle"))
    # ---- right: 查询阶段 ----
    o.append(rect(770, 186, 440, 452, "#F4FAF6", rx=14, stroke="#D3E8D9", sw=1.2))
    o.append(text(790, 214, "② 查询阶段（在线运行）", 15, GREEN, "800"))
    # 模块分组：理解编译 / 执行规划 / 输出
    o.append(rect(784, 226, 412, 152, "#ECF6F0", rx=10, stroke="#D2E6D8", sw=1))
    o.append(text(800, 246, "模块A 理解与编译", 11.5, GREEN, "700"))
    o.append(rect(784, 382, 412, 152, "#EDF7F8", rx=10, stroke="#CDE4E8", sw=1))
    o.append(text(800, 402, "模块B 执行规划", 11.5, TEAL, "700"))
    o.append(rect(784, 538, 412, 74, "#EFF8F2", rx=10, stroke="#D4E8D9", sw=1))
    o.append(text(800, 558, "模块C 答案输出", 11.5, GREEN, "700"))
    q = [("问题", "自然语言", NAVY), ("SQG 逻辑算子图", "大模型编译“想干什么”", PURPLE),
         ("优化器", "校验 · 绑定 · 优化", ORANGE), ("执行器", "在两层图/存储上跑物理算子", TEAL),
         ("答案 + 溯源", "逐条 fullname", GREEN)]
    for i, (t, s, c) in enumerate(q):
        y = 232 + i * 78
        o.append(card(790, y, 400, 60, accent=c, shadow=False))
        o.append(text(812, y + 27, t, 15.5, INK, "800"))
        o.append(text(812, y + 48, s, 12.5, MUTE, "500"))
        if i < len(q) - 1:
            o.append(arrow(820, y + 58, 820, y + 80, c, 2.4))
    # 读取：执行器 -> 三个存储（按物理算子）
    o.append(text(742, 280, "读取路径", 11.5, MUTE, "700", anchor="middle"))
    # 执行器 -> 实体索引（Search 精确）
    o.append('<path d="M790,496 C760,482 744,420 724,324" stroke="#1470C4" stroke-width="2" stroke-dasharray="4 3" fill="none" marker-end="url(#arrow)" stroke-linecap="round"/>')
    o.append(text(756, 338, "Search(精确)", 10.2, BLUE, "700", anchor="end"))
    # 执行器 -> 边表 / 图（Traverse / Lift）
    o.append('<path d="M790,496 C760,490 744,452 724,410" stroke="#0E9C9C" stroke-width="2" stroke-dasharray="4 3" fill="none" marker-end="url(#arrowt)" stroke-linecap="round"/>')
    o.append(text(752, 424, "Traverse/Lift", 10.2, TEAL, "700", anchor="end"))
    # 执行器 -> 块向量+原文（Search 向量 / Ground）
    o.append('<path d="M790,496 C760,506 744,512 724,508" stroke="#2E9E6B" stroke-width="2" stroke-dasharray="4 3" fill="none" marker-end="url(#arrowg)" stroke-linecap="round"/>')
    o.append(text(752, 522, "Search(向量)/Ground", 10.2, GREEN, "700", anchor="end"))
    return svg("".join(o))


# ============================================================ TWO-LAYER
def two_layer():
    o = [cap("两层图：实体层放“概念节点”（结构关系住这），块层放“原文片段”（向量入口/溯源），evidence 边把两层连起来。")]
    # entity layer
    o.append(rect(70, 182, 1140, 150, "#E8F3F0", rx=14, stroke="#C9E4DD", sw=1))
    o.append(text(90, 208, "① 实体层 · 概念节点（前缀=类型；结构关系挂这里；关系存一次，反向靠遍历）", 14, TEAL, "800"))
    o.append(node(120, 232, 160, 52, "AppType:IND", BLUE_SOFT, BLUE, sub="申报类型"))
    o.append(node(560, 232, 160, 52, "AppType:NDA", BLUE_SOFT, BLUE, sub="申报类型"))
    o.append(node(340, 232, 160, 52, "Reg:GCP", TEAL_SOFT, TEAL, sub="法规"))
    o.append(node(800, 232, 170, 52, "Reg:药品管理法", TEAL_SOFT, TEAL, sub="法规"))
    o.append(node(1000, 232, 170, 52, "Category:细胞治疗", GREEN_SOFT, GREEN, sub="分类"))
    o.append(arrow(280, 250, 338, 250, TEAL, 2))
    o.append(text(309, 243, "requires", 10.5, MUTE, "700", anchor="middle"))
    o.append(arrow(560, 250, 502, 250, TEAL, 2))
    o.append(text(531, 243, "requires", 10.5, MUTE, "700", anchor="middle"))
    # block layer
    o.append(rect(70, 360, 1140, 210, "#F4F8FD", rx=14, stroke="#DCE7F3", sw=1))
    o.append(text(90, 386, "② 块层 · 原文片段（fullname 层级地址；向量检索入口；细粒度引用挂这里）", 14, BLUE, "800"))
    blocks = [("IND.药品注册管理办法.临床章.b07", "“临床试验应遵守《GCP》…”", 120),
              ("GCP.药物临床试验质量管理规范.总则.b01", "“本规范适用于…”", 470),
              ("GCP.….定义.b02", "术语定义…", 820)]
    for (fn, tx, x) in blocks:
        o.append(rect(x, 408, 330, 84, PANEL, rx=10, stroke="#DDE7F2", sw=1.2))
        o.append(rect(x, 408, 5, 84, BLUE, rx=2))
        o.append(text(x + 18, 432, fn, 12, NAVY, "700", ff=MONO))
        o.append(text(x + 18, 458, tx, 13, MUTE, "500"))
        o.append(rect(x + 250, 462, 62, 20, BLUE_SOFT, rx=5))
        o.append(text(x + 281, 476, "vector", 10.5, BLUE, "700", anchor="middle"))
    # evidence: Reg:GCP -> b01（GCP 自己的总则原文）；references: b07（IND块“应遵守GCP”） -> Reg:GCP
    o.append(arrow(470, 286, 600, 406, TEAL, 1.8, dash="5 4", marker="arrowt"))
    o.append(text(614, 348, "evidence（实体→块）", 11.5, TEAL, "700"))
    o.append(arrow(300, 406, 405, 286, BLUE, 1.8, dash="5 4"))
    o.append(text(150, 348, "references（块→实体）", 11.5, BLUE, "700"))
    # legend
    o.append(rect(70, 588, 1140, 52, "#0E2E52", rx=12))
    o.append(text(92, 620, "前缀=实体类型（AppType/Reg/Category）只出现在实体层；fullname=块的层级地址只出现在块层；两层用 evidence 边相连。",
                  14, "#DCEBFA", "700"))
    return svg("".join(o))


# ============================================================ STORES × ACCURACY
def stores_accuracy():
    o = [cap("三个存储各司其职：AI Search 找到相关、实体索引认准同一个、边表/图理清关系——三者接力，把准确率撑起来。")]
    cols = [
        ("search", "AI Search（块向量＋原文）", "语义进门 · 高召回", GREEN,
         [("是什么", "原文切块＋向量＋fullname，一次调用兼做检索/过滤/重排。"),
          ("怎么用", "语义进门找相关、取原文溯源、过滤下推早筛。"),
          ("更准在哪", "不靠关键词也能召回相关；语义重排把最相关的顶上来。")]),
        ("key", "实体索引", "认准同一个 · 消歧归一", BLUE,
         [("是什么", "每个概念一份唯一档案：名称＋别名＋属性。"),
          ("怎么用", "精确/别名进门、按属性筛选、发稳定 id。"),
          ("更准在哪", "别名再多都锚定到唯一节点：同物不重复、异物不混淆。")]),
        ("relate", "边表 / 图", "理清关系 · 找全可核对", TEAL,
         [("是什么", "概念间的有向类型关系(requires…)，只存一次。"),
          ("怎么用", "沿关系多跳遍历、列全；块与实体互相定位。"),
          ("更准在哪", "关系可确定性遍历：找得全、能核对，不靠模型脑补。")]),
    ]
    xs, cw, cy, ch = [70, 457, 844], 366, 182, 316
    for k, (ic, title, tag, c, secs) in enumerate(cols):
        x = xs[k]
        o.append(card(x, cy, cw, ch, accent=c))
        o.append(disc(x + 46, cy + 44, 22, SOFT[c]))
        o.append(ico(ic, x + 46, cy + 44, 16, c))
        o.append(text(x + 80, cy + 38, title, 16, INK, "800"))
        o.append(text(x + 80, cy + 60, tag, 11.5, c, "700"))
        o.append(line(x + 22, cy + 80, x + cw - 22, cy + 80, LINE, 1))
        sy = cy + 92
        for (lab, body) in secs:
            emph = lab == "更准在哪"
            o.append(rect(x + 22, sy, 70, 22, SOFT[c], rx=6))
            o.append(text(x + 57, sy + 15, lab, 11, c, "800", anchor="middle"))
            lines = wrapw(body, 21)
            for j, ln in enumerate(lines):
                o.append(text(x + 100, sy + 15 + j * 17, ln, 12, c if emph else MUTE,
                              "700" if emph else "600"))
            sy += max(30, 8 + len(lines) * 17) + 14
    # ---- bottom cooperation band ----
    o.append(rect(70, 516, 1140, 152, "#0E2E52", rx=14))
    o.append(text(92, 548, "为什么合起来更准 —— 每一层补上另一层的短板", 15, "#8FD3FF", "800"))
    chips = [("① 向量召回", "AI Search 找到相关候选", GREEN),
             ("② 归一锚定", "实体索引 收敛别名、消歧", BLUE),
             ("③ 遍历找全", "边表/图 顺关系列全并核对", TEAL),
             ("④ 取证溯源", "块原文 回原文对齐 fullname", ORANGE)]
    cxw, cgap, cx0 = 250, 24, 90
    for i, (t, d, c) in enumerate(chips):
        x = cx0 + i * (cxw + cgap)
        o.append(rect(x, 566, cxw, 56, "#173D64", rx=10))
        o.append(rect(x, 566, 5, 56, c, rx=2))
        o.append(text(x + 18, 590, t, 14, "#EAF3FF", "800"))
        o.append(text(x + 18, 610, d, 11.5, "#A9C4DE", "600"))
        if i < len(chips) - 1:
            o.append(text(x + cxw + cgap / 2, 598, "›", 20, "#5E82A6", "800", anchor="middle"))
    o.append(text(92, 652,
                  "向量负责召回、实体负责精确、图负责完整、原文负责可核对 —— 四者相乘，才是稳定的高正确率。",
                  13, "#DCEBFA", "700"))
    return svg("".join(o))


# ============================================================ STORE DETAIL HELPERS
def _why_how(why, how):
    o = []
    for (x, ic, ttl, c, items) in [(70, "gear", "为什么这么存", ORANGE, why),
                                    (643, "search", "怎么检索", TEAL, how)]:
        o.append(card(x, 486, 567, 180, accent=c))
        o.append(disc(x + 44, 516, 18, SOFT[c]))
        o.append(ico(ic, x + 44, 516, 13, c))
        o.append(text(x + 74, 522, ttl, 16, INK, "800"))
        yy = 550
        for it in items:
            o.append(circle(x + 32, yy - 4, 3, fill=c))
            lines = wrapw(it, 42)
            for j, ln in enumerate(lines):
                o.append(text(x + 46, yy + j * 16, ln, 12, MUTE, "600"))
            yy += max(20, len(lines) * 16) + 6
    return "".join(o)


def _record(x, y, w, h, key, keyc, tag, rows):
    o = rect(x, y, w, h, "#FBFCFE", rx=12, stroke=keyc, sw=1.4)
    kw = len(key) * 8.6 + 24
    o += pill(x + 16, y + 14, kw, 28, keyc, key, 13, "#FFFFFF", "800")
    o += text(x + 16 + kw + 12, y + 33, tag, 12, MUTE, "600")
    for i, (lab, val, hl) in enumerate(rows):
        ry = y + 62 + i * 30
        o += text(x + 20, ry, lab, 11.5, keyc, "800")
        if hl:
            o += text(x + 96, ry, val, 12.5, keyc, "800", ff=MONO)
        else:
            o += text(x + 96, ry, val, 12.5, INK, "600")
    return o


# ============================================================ STORE A · 实体索引
def entity_store():
    o = [cap("实体索引长什么样：一张以「名称 / 别名」为键的概念档案表，同一概念只存一条，并发给它一个稳定 id。")]
    o.append(card(70, 182, 1140, 286, accent=BLUE))
    o.append(text(94, 214, "长这样 · 概念档案（key = 名称 / 别名 → 唯一记录）", 15, BLUE, "800"))
    # left: many names -> one record
    o.append(text(100, 250, "多个叫法", 11.5, MUTE, "700"))

    def _cjkw(s, sz):
        return sum(sz * (0.6 if ord(c) < 128 else 1.02) for c in s)
    for i, nm in enumerate(["“GCP”", "“药物临床试验管理规范”", "“药物临床试验质量管理规范”"]):
        yy = 268 + i * 40
        wch = _cjkw(nm, 11.5) + 22
        o.append(rect(100, yy, wch, 26, PANEL, rx=6, stroke=BLUE, sw=1.2))
        o.append(text(100 + wch / 2, yy + 17, nm, 11.5, BLUE, "700", anchor="middle"))
        o.append(arrow(100 + wch + 6, yy + 13, 302, 300, BLUE, 1.6, dash="4 3"))
    # record 1: Reg:GCP
    o.append(_record(310, 250, 400, 200, "Reg:GCP", TEAL, "法规（实体节点）",
                     [("规范名", "药物临床试验质量管理规范", False),
                      ("别名", "GCP · 药物临床试验管理规范", False),
                      ("属性", "status=现行有效 · type=部门规章", False),
                      ("id", "reg_gcp_001", True)]))
    # record 2: AppType:IND
    o.append(_record(740, 250, 400, 200, "AppType:IND", BLUE, "申报类型（实体节点）",
                     [("全称", "新药临床试验申请", False),
                      ("别名", "IND · Investigational New Drug", False),
                      ("属性", "stage=临床前 / 早期", False),
                      ("id", "app_ind_001", True)]))
    o.append(_why_how(
        ["概念只留一份：同一法规的多个叫法合并成一条，天然去重归一。",
         "别名全挂在这条上：换个说法也命中同一节点。",
         "属性字段化：status / type 直接用于筛选。",
         "发放稳定 id：边表和块存储都用它引用，全局对齐。"],
        ["名字 / 别名 → 规范化 → 哈希精确查 O(1) → 唯一 id。",
         "精确名未命中，则查别名表 aliases。",
         "按属性枚举 / 过滤：type=Reg、status=现行。",
         "输出的 id → 交给边表遍历，或交给块存储取原文。"]))
    return svg("".join(o))


# ============================================================ STORE B · 边表/图
def edge_store():
    o = [cap("边 = 概念之间「有向 + 带类型」的关系。共五种边，每种在图上都有示例，颜色与右侧清单一一对应。")]
    o.append(card(70, 182, 1140, 286, accent=TEAL))
    o.append(text(94, 214, "长这样 · 一张有向类型图（左：示例图；右：五种边清单）", 15, TEAL, "800"))
    # ---- graph (left) ----
    o.append(text(110, 240, "实体层 · 概念节点", 10.5, MUTE, "700"))
    R = {}

    def gn(name, x, y, w, h, label=None, fill="#FFFFFF"):
        R[name] = (x, y, w, h)
        return (rect(x, y, w, h, fill, rx=9, stroke="#93A6BD", sw=1.5)
                + text(x + w / 2, y + h / 2 + 4.5, label or name, 12, NAVY, "800", anchor="middle"))
    o.append(gn("IND", 110, 250, 96, 38, "IND"))
    o.append(gn("GCP", 300, 246, 96, 38, "GCP"))
    o.append(gn("细胞治疗", 474, 246, 118, 38, "细胞治疗"))
    o.append(gn("药品管理法", 110, 356, 132, 38, "药品管理法"))
    o.append(gn("GCP旧", 300, 344, 116, 34, "GCP·旧版"))
    o.append(text(474, 356, "块层 · 原文片段", 10.5, MUTE, "700"))
    o.append(gn("块", 470, 362, 202, 38, "块 GCP.总则.b01", fill="#EEF4FB"))

    def _cjkw(s, sz):
        return sum(sz * (0.6 if ord(c) < 128 else 1.02) for c in s)

    def b2(name, tx, ty):
        x, y, w, h = R[name]; cx, cy = x + w / 2, y + h / 2
        dx, dy = tx - cx, ty - cy
        if dx == 0 and dy == 0:
            return cx, cy
        sx = (w / 2 + 5) / abs(dx) if dx else 1e9
        sy = (h / 2 + 5) / abs(dy) if dy else 1e9
        s = min(sx, sy)
        return cx + dx * s, cy + dy * s

    MK = {TEAL: "arrowt", GREEN: "arrowg", ORANGE: "arrowo", PURPLE: "arrowp", BLUE: "arrow"}

    def ed(a, b, lab, c, bidir=False):
        ax, ay = R[a][0] + R[a][2] / 2, R[a][1] + R[a][3] / 2
        bx, by = R[b][0] + R[b][2] / 2, R[b][1] + R[b][3] / 2
        x1, y1 = b2(a, bx, by); x2, y2 = b2(b, ax, ay)
        frag = arrow(x1, y1, x2, y2, c, 1.9, marker=MK[c])
        if bidir:
            frag += arrow(x2, y2, x1, y1, c, 1.9, marker=MK[c])
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        w = _cjkw(lab, 10.5) + 14
        frag += rect(mx - w / 2, my - 10, w, 20, "#FFFFFF", rx=5, stroke=c, sw=1)
        frag += text(mx, my + 4, lab, 10.5, c, "800", anchor="middle")
        return frag
    o.append(ed("IND", "GCP", "要求", TEAL))
    o.append(ed("IND", "药品管理法", "要求", TEAL))
    o.append(ed("GCP", "细胞治疗", "归类", GREEN))
    o.append(ed("GCP", "GCP旧", "替代", ORANGE))
    o.append(ed("药品管理法", "GCP", "引用", PURPLE))
    o.append(ed("GCP", "块", "出处", BLUE, bidir=True))
    o.append(text(96, 462, "关系只存一次（有向）；反向（谁「要求」我）靠遍历，不另存。", 10.5, MUTE, "600"))
    # ---- legend: five edge types (right) ----
    lx = 800
    o.append(text(lx, 232, "五种边（关系）· 一句话看懂", 13.5, INK, "800"))
    legend = [
        (TEAL, "要求", "requires", "申报类型 → 该遵守的法规（IND 要 GCP）"),
        (GREEN, "归类", "belongs_to", "法规 → 所属主题分类（GCP 属 细胞治疗）"),
        (ORANGE, "替代", "supersedes", "新版法规 → 被它取代的旧版"),
        (PURPLE, "引用", "references", "一条法规文本里提到 / 引用另一条"),
        (BLUE, "出处", "evidence", "概念 ↔ 它的原文块（双向：取原文 / 抬升）"),
    ]
    for i, (c, cn, en, desc) in enumerate(legend):
        y = 250 + i * 39
        o.append(rect(lx, y, 16, 16, c, rx=4))
        o.append(text(lx + 26, y + 13, cn, 13, c, "800"))
        o.append(text(lx + 26 + _cjkw(cn, 13) + 8, y + 13, en, 11, MUTE, "700", ff=MONO))
        o.append(text(lx + 26, y + 31, desc, 11, MUTE, "600"))
    o.append(text(lx, 458, "物理上 = 一张边表（源 ｜ 类型 ｜ 目标 ｜ 权重），每条关系存一行。", 10.5, FAINT, "700"))
    o.append(_why_how(
        ["关系只存一次（有向一行）：无冗余、省空间、好维护。",
         "边带类型：要求 / 归类 / 替代 / 引用 / 出处，可分别遍历。",
         "边带权重：支持带权扩散与相关度排序。",
         "反向关系不另存：需要时反向遍历即可。"],
        ["从起点实体沿某类型边遍历 / 带权扩散（Traverse），可多跳。",
         "反向查 = 换方向遍历（谁「要求」我）。",
         "块 ↔ 实体：走「出处」边（Lift 抬升 / Ground 取原文）。",
         "多跳 = 沿边接力；带权累乘用于剪枝与排序。"]))
    return svg("".join(o))


# ============================================================ STORE C · 块向量+原文
def block_store():
    o = [cap("AI Search 长什么样：法规原文切成小块，每块带 fullname 地址 + 向量 + 元数据；一个索引兼做检索 / 过滤 / 重排。")]
    o.append(card(70, 182, 1140, 286, accent=GREEN))
    o.append(text(94, 214, "长这样 · 块 = 原文片段 + 向量 + fullname（左：块记录；右：向量空间）", 15, GREEN, "800"))
    # ---- chunk records (left) ----
    def chunk(x, y, w, h, fn, tx, fields):
        r = rect(x, y, w, h, "#FBFCFE", rx=10, stroke=GREEN, sw=1.3)
        r += rect(x, y, 5, h, GREEN, rx=2)
        r += text(x + 18, y + 24, "fullname: " + fn, 11.5, NAVY, "800", ff=MONO)
        r += text(x + 18, y + 44, tx, 12, INK, "600")
        r += text(x + 18, y + 64, "vector: [0.12, -0.03, 0.88, …]  3072 维", 11, TEAL, "700", ff=MONO)
        r += text(x + 18, y + 84, fields, 11, MUTE, "600", ff=MONO)
        return r
    o.append(chunk(94, 242, 540, 104, "GCP.总则.b01", "“本规范适用于药物临床试验的全过程…”",
                   "type=Reg · status=现行 · reg_id=reg_gcp_001"))
    o.append(chunk(94, 356, 540, 100, "IND.药品注册管理办法.临床章.b07", "“临床试验应遵守《GCP》…”",
                   "type=Reg · status=现行 · reg_id=reg_ndaadmin"))
    # ---- vector space (right) ----
    vx, vy, vw, vh = 700, 240, 490, 218
    o.append(rect(vx, vy, vw, vh, "#F4F9F6", rx=12, stroke=GREEN_SOFT, sw=1.4))
    o.append(text(vx + 18, vy + 26, "向量空间：语义相近 → 相邻（ANN 找最近的块）", 12, GREEN, "800"))
    qx, qy = vx + 150, vy + 130
    near = [(qx - 70, qy - 40), (qx - 30, qy + 55), (qx + 60, qy - 20)]
    far = [(vx + 380, vy + 60), (vx + 420, vy + 150), (vx + 330, vy + 170), (vx + 300, vy + 55)]
    for (px, py) in far:
        o.append(circle(px, py, 9, fill="#C6D2E0"))
    for (px, py) in near:
        o.append(line(qx, qy, px, py, GREEN, 1.5, dash="3 3"))
        o.append(circle(px, py, 10, fill=GREEN))
    o.append(circle(qx, qy, 15, fill=RED))
    o.append(text(qx, qy + 5, "q", 13, "#FFFFFF", "800", anchor="middle"))
    o.append(text(qx, qy + 34, "查询向量", 10.5, RED, "700", anchor="middle"))
    o.append(text(vx + 300, vy + 200, "绿点 = 命中 Top-k　灰点 = 其他块", 10.5, MUTE, "600", anchor="middle"))
    o.append(_why_how(
        ["切成小块：可引用的最小单元，答案能精确定位到条 / 款。",
         "fullname 地址：块知道自己在文档树的位置 → 可溯源、可排序。",
         "向量：语义相近就相邻，能召回「意思对但用词不同」的内容。",
         "元数据随块存：type / status / id → 过滤下推、回连实体。"],
        ["embed(查询) → HNSW 近邻搜索找最相近的块（ANN）。",
         "$filter 下推：先按 type / status 早筛，再算相似度。",
         "语义重排（queryType=semantic）把最相关的顶上来，取 Top-k。",
         "命中块 → 按 fullname 溯源，或 Lift 抬到实体层走关系。"]))
    return svg("".join(o))


# ============================================================ EFFORT / 工时
def effort_plan():
    o = [cap("按模块拆分的工时估算（单位：小时）。合计约 260 小时，核心在「查询编译与执行」。")]
    phases = [
        ("A", "数据与索引（离线）", 60, BLUE,
         [("语义切块 + fullname", 12), ("实体抽取与归一", 16),
          ("LLM 建边（关系裁定）", 18), ("块向量化 + 入库", 14)]),
        ("B", "存储与检索底座", 40, TEAL,
         [("AI Search 索引（向量/语义/过滤/别名）", 16),
          ("边表 / 图存储 + 遍历接口", 14), ("实体索引（精确/别名/属性）", 10)]),
        ("C", "查询编译与执行（核心）", 80, PURPLE,
         [("SQG 逻辑算子 + LLM 编译", 20), ("优化器（校验/绑定/下推/并行）", 22),
          ("Search 封装 + Lift/Ground/Traverse", 26), ("集合 / LLM 加工 / 校验控制", 12)]),
        ("D", "集成与可视化", 35, GREEN,
         [("端到端串联（问题→答案+溯源）", 14), ("算子级 trace / 可排查", 12),
          ("溯源与 fullname 回填", 9)]),
        ("E", "评估与调优", 25, ORANGE,
         [("评测集（正确率/覆盖率/溯源率）", 12), ("调参 / 回归 / 误差分析", 13)]),
        ("F", "项目管理与缓冲", 20, NAVY,
         [("设计评审 / 文档", 10), ("联调 / 部署 / 缓冲", 10)]),
    ]
    x0, y0, cw, ch, gx, gy = 70, 178, 366, 174, 21, 16
    for i, (lt, name, hrs, c, subs) in enumerate(phases):
        col, row = i % 3, i // 3
        x, y = x0 + col * (cw + gx), y0 + row * (ch + gy)
        o.append(card(x, y, cw, ch, accent=c))
        o.append(disc(x + 40, y + 34, 16, SOFT[c]))
        o.append(text(x + 40, y + 39, lt, 14.5, c, "800", anchor="middle"))
        o.append(text(x + 66, y + 32, name, 14.5, INK, "800"))
        o.append(pill(x + cw - 82, y + 18, 64, 27, c, f"{hrs}h", 14, "#FFFFFF", "800"))
        o.append(line(x + 22, y + 54, x + cw - 22, y + 54, LINE, 1))
        yy = y + 78
        for (tn, th) in subs:
            o.append(circle(x + 30, yy - 4, 2.5, fill=c))
            o.append(text(x + 40, yy, tn, 12, MUTE, "600"))
            o.append(text(x + cw - 24, yy, f"{th}h", 12, INK, "800", anchor="end"))
            yy += 24
    # ---- total banner + stacked proportion bar ----
    o.append(rect(70, 566, 1140, 96, "#0E2E52", rx=14))
    o.append(text(92, 606, "合计 260 小时", 19, "#FFFFFF", "800"))
    o.append(text(268, 606, "≈ 6.5 人周（按 40h/周）　·　核心「查询编译与执行」80h 占比最高",
                  13, "#A9C4DE", "600"))
    bx, bw, by = 92, 1096, 622
    sc = bw / 260.0
    cx = bx
    for (lt, name, hrs, c, _) in phases:
        w = hrs * sc
        o.append(rect(cx, by, w - 3, 26, c, rx=5))
        o.append(text(cx + (w - 3) / 2, by + 17, f"{lt} {hrs}h", 11.5, "#FFFFFF", "800", anchor="middle"))
        cx += w
    return svg("".join(o))


# ============================================================ INDEX FLOW
def index_flow():
    o = [cap("索引阶段：把原始法规文本一步步加工成“实体层 + 块层”的两层图，并落入三个存储。")]
    sx = [70, 300, 530, 760, 990]
    sw, sy, sh = 210, 178, 246

    def panel(x, num, title, color):
        p = card(x, sy, sw, sh, accent=color)
        if num:
            p += circle(x + 30, sy + 30, 14, fill=color)
            p += text(x + 30, sy + 36, num, 14, "#FFFFFF", "800", anchor="middle")
            p += text(x + 52, sy + 35, title, 13.5, INK, "800")
        else:
            p += text(x + 24, sy + 35, title, 14, INK, "800")
        return p

    for i in range(4):
        o.append(arrow(sx[i] + sw + 1, sy + 120, sx[i + 1] - 1, sy + 120, MUTE, 2.4))
    # Stage 0 原文
    x = sx[0]; o.append(panel(x, "", "原始法规文本", BLUE))
    o.append(rect(x + 26, sy + 60, sw - 52, 150, "#F7FAFE", rx=8, stroke="#DCE6F2", sw=1))
    for i in range(5):
        o.append(rect(x + 42, sy + 78 + i * 24, sw - 84, 9, "#CBD8E8", rx=4))
    # Stage 1 切块
    x = sx[1]; o.append(panel(x, "①", "语义切块", BLUE))
    for i, fn in enumerate(["IND.…临床章.b07", "GCP.…总则.b01", "GCP.…定义.b02"]):
        o.append(rect(x + 20, sy + 64 + i * 46, sw - 40, 38, "#EEF4FB", rx=7, stroke="#DCE6F2", sw=1))
        o.append(rect(x + 20, sy + 64 + i * 46, 4, 38, BLUE, rx=2))
        o.append(text(x + 32, sy + 87 + i * 46, fn, 10.5, NAVY, "700", ff=MONO))
    o.append(text(x + sw / 2, sy + 226, "每块赋 fullname", 12, BLUE, "700", anchor="middle"))
    # Stage 2 抽实体+归一
    x = sx[2]; o.append(panel(x, "②", "抽实体 + 归一", TEAL))
    o.append(pill(x + 26, sy + 60, sw - 52, 32, TEAL_SOFT, "Reg:GCP", 13.5, TEAL, "800"))
    o.append(pill(x + 26, sy + 100, sw - 52, 32, BLUE_SOFT, "AppType:IND", 13.5, BLUE, "800"))
    o.append(rect(x + 20, sy + 148, sw - 40, 62, "#FFF6EC", rx=8, stroke=ORANGE, sw=1))
    o.append(text(x + 30, sy + 170, "GCP · 《药物临床…》", 10.5, MUTE, "600"))
    o.append(text(x + 30, sy + 187, "· 临床试验规范", 10.5, MUTE, "600"))
    o.append(text(x + 30, sy + 205, "→ 归一到 1 个节点", 11, ORANGE, "800"))
    # Stage 3 LLM建边
    x = sx[3]; o.append(panel(x, "③", "LLM 建边", PURPLE))
    o.append(node(x + 18, sy + 74, 74, 34, "IND", BLUE_SOFT, BLUE, tsize=13))
    o.append(node(x + 116, sy + 74, 74, 34, "GCP", TEAL_SOFT, TEAL, tsize=13))
    o.append(text(x + sw / 2, sy + 66, "requires", 10.5, MUTE, "700", anchor="middle"))
    o.append(arrow(x + 94, sy + 91, x + 114, sy + 91, TEAL, 2))
    o.append(text(x + sw / 2, sy + 152, "候选提名 + LLM 裁定", 11.5, PURPLE, "700", anchor="middle"))
    o.append(text(x + sw / 2, sy + 174, "关系存一次 · 反向靠遍历", 10.5, MUTE, "600", anchor="middle"))
    # Stage 4 向量化
    x = sx[4]; o.append(panel(x, "④", "块向量化", GREEN))
    o.append(rect(x + 55, sy + 62, 100, 32, PANEL, rx=7, stroke=GREEN, sw=1.2))
    o.append(text(x + 105, sy + 83, "块 b07", 12, INK, "700", anchor="middle"))
    o.append(arrow(x + 105, sy + 96, x + 105, sy + 118, GREEN, 2))
    for k in range(8):
        o.append(rect(x + 26 + k * 20, sy + 124, 16, 16, GREEN, rx=3, opacity=0.30 + 0.10 * (k % 3)))
    o.append(text(x + sw / 2, sy + 174, "text-embedding · 3072 维", 10.5, GREEN, "700", anchor="middle"))
    # down arrows + stores
    o.append(arrow(635, sy + sh + 2, 635, sy + sh + 40, MUTE, 2.4))
    o.append(arrow(865, sy + sh + 2, 865, sy + sh + 40, MUTE, 2.4))
    o.append(arrow(1095, sy + sh + 2, 1095, sy + sh + 40, MUTE, 2.4))
    ys = sy + sh + 42
    o.append(store_cyl(525, ys, 220, 84, "实体索引", "名称 / 别名 / 属性", BLUE, "#EAF2FC"))
    o.append(store_cyl(755, ys, 220, 84, "边表 / 图", "requires · evidence…", TEAL, "#E4F4F2"))
    o.append(store_cyl(985, ys, 225, 84, "块向量 + 原文", "向量 · text · fullname", GREEN, "#E3F4EA"))
    o.append(rect(70, ys, 435, 84, PANEL, rx=12, stroke=LINE, sw=1))
    o.append(rect(70, ys, 6, 84, PURPLE, rx=3))
    o.append(text(92, ys + 28, "建边只用 LLM", 14, INK, "800"))
    o.append(text(92, ys + 50, "便宜手段只提名候选（保召回），判定权全给 LLM（保精度）；", 12, MUTE, "600"))
    o.append(text(92, ys + 70, "切块产出的块 → 落入“块向量 + 原文”存储。", 12, MUTE, "600"))
    return svg("".join(o))


# ============================================================ QUERY PIPELINE
def query_pipeline():
    o = [cap("查询阶段三段式：大模型只写“想干什么”的算子图(SQG)；优化器绑定成物理算子并优化；执行器在两层图/存储上跑。")]
    # stage 1 SQG
    o.append(rect(70, 184, 360, 300, PURPLE_SOFT, rx=14, stroke=PURPLE, sw=1.4))
    o.append(text(90, 212, "① SQG · 逻辑算子图", 16, PURPLE, "800"))
    o.append(text(90, 234, "大模型写“想干什么”，可见可排查", 12, MUTE, "500"))
    for i, (t) in enumerate(["检索 / 关联", "筛选 / 对比", "汇总 / 校验", "回答"]):
        y = 252 + i * 52
        o.append(rect(96, y, 300, 42, PANEL, rx=9, stroke="#D9CEF0", sw=1))
        o.append(text(116, y + 27, t, 14.5, INK, "700"))
    o.append(text(96, 476, "算子=一句人话；依赖=思考顺序", 12, PURPLE, "600"))
    o.append(arrow(432, 334, 470, 334, MUTE, 2.6))
    # stage 2 optimizer
    o.append(rect(474, 184, 300, 300, ORANGE_SOFT, rx=14, stroke=ORANGE, sw=1.4))
    o.append(text(494, 212, "② 优化器", 16, ORANGE, "800"))
    for i, s in enumerate(["校验（无环/类型/参数）", "绑定：逻辑→物理算子",
                            "优化：下推·并行·惰性取原文·缓存", "编排成可执行 DAG"]):
        y = 240 + i * 56
        o.append(rect(490, y, 268, 44, PANEL, rx=9, stroke="#F0DFC7", sw=1))
        for j, ln in enumerate(wrapw(s, 16)):
            o.append(text(506, y + (27 if len(wrapw(s, 16)) == 1 else 19 + j * 16), ln, 13, INK, "600"))
    o.append(arrow(776, 334, 814, 334, MUTE, 2.6))
    # stage 3 executor
    o.append(rect(818, 184, 392, 300, TEAL_SOFT, rx=14, stroke=TEAL, sw=1.4))
    o.append(text(838, 212, "③ 执行器（物理算子）", 16, TEAL, "800"))
    o.append(text(838, 234, "检索侧＝一个 Search 算子（AI Search）", 12, MUTE, "500"))
    for i, s in enumerate(["Search（AI Search 一次调用）", "Lift / Ground / Traverse",
                           "Intersect / Diff / Union", "LLM生成 / 校验"]):
        y = 252 + i * 50
        o.append(rect(838, y, 352, 40, PANEL, rx=9, stroke="#CFE9E6", sw=1))
        o.append(text(856, y + 26, s, 13.5, INK, "700", ff=MONO))
    # stores + answer
    o.append(store_cyl(70, 510, 360, 70, "读三存储", "实体索引 · 边表/图 · 块向量+原文", NAVY, "#EAF0F7"))
    o.append(arrow(600, 500, 600, 520, MUTE, 2.4))
    o.append(rect(474, 512, 736, 68, "#0E2E52", rx=12))
    o.append(text(500, 538, "输出：答案 + 每条 fullname 溯源。", 13.5, "#DCEBFA", "700"))
    o.append(text(500, 562, "执行前看 SQG＝大模型想走的每一步；执行后每步回填实际输出＝哪步跑偏一眼定位。", 13, "#AFC6DE", "600"))
    return svg("".join(o))


# ---------------- shared example helpers ----------------
def op_node(x, y, w, label, color, soft, h=52):
    o = rect(x, y, w, h, soft, rx=10, stroke=color, sw=1.5)
    for j, ln in enumerate(wrapw(label, int((w - 16) / 8.4))):
        o += text(x + w / 2, y + h / 2 + 5 - (len(wrapw(label, int((w - 16) / 8.4))) - 1) * 9 + j * 18,
                  ln, 13.5, INK, "700", anchor="middle")
    return o


def onode(x, y, w, h, label, color, fs=13):
    """Pretty operator node: white rounded card + left accent + soft shadow."""
    o = f'<g filter="url(#sh)">{rect(x, y, w, h, PANEL, rx=11, stroke="#E4EBF4", sw=1)}</g>'
    o += rect(x, y, 5, h, color, rx=2.5)
    lines = wrapw(label, max(6, int((w - 26) / (fs * 0.6))))
    yy = y + h / 2 + fs * 0.34 - (len(lines) - 1) * (fs + 2) / 2
    for ln in lines:
        o += text(x + 15 + (w - 15) / 2, yy, ln, fs, INK, "700", anchor="middle")
        yy += fs + 2
    return o


def scard(x, y, w, h, label, color, soft):
    """Store card with a small DB-cylinder icon."""
    cx, cy = x + 24, y + h / 2
    o = f'<g filter="url(#sh)">{rect(x, y, w, h, soft, rx=10, stroke=color, sw=1.5)}</g>'
    o += rect(cx - 9, cy - 8, 18, 16, color)
    o += f'<ellipse cx="{cx}" cy="{cy + 8}" rx="9" ry="3.4" fill="{color}"/>'
    o += f'<ellipse cx="{cx}" cy="{cy - 8}" rx="9" ry="3.4" fill="#FFFFFF" opacity="0.6"/>'
    o += text(x + 44, cy + 5, label, 13.5, INK, "800")
    return o


# ============================================================ EX1 PLANS
def ex1_plans():
    o = [cap("例①（精确入口）问题：IND 要求、但 NDA 不要求的法规有哪些？ —— 入口是精确名，全程不查向量。")]
    # ---- left SQG ----
    o.append(rect(70, 184, 460, 448, "#FAF8FE", rx=16, stroke=PURPLE, sw=1.3))
    o.append(text(92, 214, "① 大模型写的 SQG（逻辑）", 15, PURPLE, "800"))
    o.append(onode(120, 252, 165, 50, "op1 检索 IND法规", PURPLE))
    o.append(onode(315, 252, 165, 50, "op2 检索 NDA法规", PURPLE))
    o.append(onode(215, 374, 170, 50, "op3 对比 取 IND 独有", ORANGE))
    o.append(onode(215, 478, 170, 50, "op4 回答 + 溯源", GREEN))
    o.append(arrow(203, 302, 288, 372, PURPLE, 2.2))
    o.append(arrow(397, 302, 312, 372, PURPLE, 2.2))
    o.append(arrow(300, 424, 300, 476, ORANGE, 2.2))
    o.append(text(120, 568, "读法：分别取两边法规 → 求差集 → 回答", 12.5, MUTE, "600"))
    o.append(text(120, 592, "大模型不碰向量/图，只画思路", 12.5, MUTE, "600"))
    # ---- right PEP ----
    o.append(rect(560, 184, 650, 448, "#F5FBFA", rx=16, stroke=TEAL, sw=1.3))
    o.append(text(582, 213, "② 优化器产出的物理执行计划(PEP)", 15, TEAL, "800"))
    o.append(text(582, 233, "实线 = 数据流　　虚线 = 取数（读存储）", 11.5, MUTE, "500"))
    # operators
    o.append(onode(600, 252, 150, 44, "P1 Search IND", BLUE, fs=12.5))
    o.append(onode(770, 252, 150, 44, "P2 Search NDA", BLUE, fs=12.5))
    o.append(onode(600, 324, 150, 44, "P3 Traverse requires", TEAL, fs=12))
    o.append(onode(770, 324, 150, 44, "P4 Traverse requires", TEAL, fs=12))
    o.append(onode(685, 396, 150, 44, "P5 Diff（内存）", ORANGE, fs=12.5))
    o.append(onode(685, 468, 150, 44, "P6 Ground 取原文", GREEN, fs=12.5))
    o.append(onode(685, 540, 150, 44, "P7 Answer 溯源", NAVY, fs=12.5))
    # flow arrows (solid)
    o.append(arrow(675, 296, 675, 322, BLUE, 1.9))
    o.append(arrow(845, 296, 845, 322, BLUE, 1.9))
    o.append(arrow(675, 368, 730, 394, TEAL, 1.9))
    o.append(arrow(845, 368, 790, 394, TEAL, 1.9))
    o.append(arrow(760, 440, 760, 466, ORANGE, 1.9))
    o.append(arrow(760, 512, 760, 538, GREEN, 1.9))
    # stores (right, row-aligned)
    o.append(scard(970, 252, 175, 44, "实体索引", BLUE, "#EAF2FC"))
    o.append(scard(970, 324, 175, 44, "边表 / 图", TEAL, "#E4F4F2"))
    o.append(scard(970, 456, 175, 54, "块存储 原文", GREEN, "#E3F4EA"))
    # read lines (dashed, arrow points to operator)
    o.append(arrow(968, 274, 924, 274, BLUE, 1.6, dash="4 3"))     # 实体索引 → P1/P2 行
    o.append(arrow(968, 346, 924, 346, TEAL, 1.6, dash="4 3"))     # 边表 → P3/P4 行
    o.append(arrow(968, 480, 839, 486, GREEN, 1.6, dash="4 3"))    # 块存储 → P6
    o.append(arrow(968, 350, 839, 482, TEAL, 1.6, dash="4 3"))     # 边表 → P6
    o.append(text(600, 606, "同色算子读同一存储（P1/P2 读实体索引，P3/P4 读边表）· P5 纯内存 · 惰性取原文，P1‖P2 并行",
                  11.5, MUTE, "600"))
    return svg("".join(o))


# ============================================================ EX1 EXEC
def ex1_exec():
    o = [cap("例① 逐步执行：把 IND、NDA 两个法规集合做差集（IND − NDA），只用 id 计算，最终 8 条才取原文。")]
    # ---- Venn (left) ----
    o.append(vcirc(360, 402, 165, BLUE))
    o.append(vcirc(560, 402, 165, TEAL))
    o.append(text(292, 214, "IND 申报所需", 15.5, BLUE, "800", anchor="middle"))
    o.append(text(292, 236, "共 10 条", 12.5, MUTE, "600", anchor="middle"))
    o.append(text(628, 214, "NDA 申报所需", 15.5, TEAL, "800", anchor="middle"))
    o.append(text(628, 236, "共 28 条", 12.5, MUTE, "600", anchor="middle"))
    # IND-only badge (the diff result)
    o.append(circle(258, 372, 32, fill=BLUE))
    o.append(text(258, 384, "8", 30, "#FFFFFF", "800", anchor="middle"))
    o.append(text(258, 436, "IND 独有", 13.5, BLUE, "800", anchor="middle"))
    # overlap
    o.append(text(460, 394, "共有", 12.5, "#3A4A5A", "700", anchor="middle"))
    o.append(text(460, 420, "2", 20, "#3A4A5A", "800", anchor="middle"))
    # NDA-only
    o.append(circle(662, 372, 27, fill=TEAL))
    o.append(text(662, 381, "26", 19, "#FFFFFF", "800", anchor="middle"))
    o.append(text(662, 436, "NDA 独有", 13.5, TEAL, "800", anchor="middle"))
    # connector
    o.append(arrow(300, 355, 742, 300, ORANGE, 2, dash="5 4", marker="arrowo"))
    o.append(text(430, 292, "取左侧月牙 = IND 独有", 12, ORANGE, "800"))
    # ---- result card (right) ----
    o.append(rlist_card(742, 236, 456, 300, "P5 结果：IND − NDA = 8 条",
                        ["生物制品注册受理审查指南", "人源干细胞非临床", "人源干细胞药学",
                         "人源性干细胞临床试验", "细胞治疗临床药理学", "细胞治疗研究与评价",
                         "免疫细胞药学", "免疫细胞临床试验"], ORANGE))
    # ---- answer band ----
    o.append(rect(70, 560, 1140, 58, "#0E2E52", rx=12))
    o.append(rect(70, 560, 6, 58, GREEN, rx=3))
    o.append(text(92, 584, "P6 Ground 只取这 8 条原文 → P7 回答：", 14, "#8FD3FF", "800"))
    o.append(text(92, 606, "“IND 要求、NDA 不要求的法规有 8 部……”，逐条列出并各附 fullname 出处。", 12.5, "#DCEBFA", "600"))
    return svg("".join(o))


# ============================================================ EX2 PLANS
def ex2_plans():
    o = [cap("例②（向量入口）问题：和细胞治疗相关的法规里，哪些是 IND 申报要求的？ —— “细胞治疗”走向量，“IND”走精确。")]
    # ---- left SQG ----
    o.append(rect(70, 184, 460, 448, "#FAF8FE", rx=16, stroke=PURPLE, sw=1.3))
    o.append(text(92, 214, "① 大模型写的 SQG（逻辑）", 15, PURPLE, "800"))
    o.append(onode(112, 252, 200, 50, "op1 检索 细胞治疗相关法规", RED, fs=12))
    o.append(text(120, 322, "↑ 语义主题 → 要查向量", 11.5, RED, "700"))
    o.append(onode(330, 252, 160, 50, "op2 检索 IND法规", PURPLE))
    o.append(text(340, 322, "↑ 精确名 → 不查向量", 11.5, PURPLE, "700"))
    o.append(onode(215, 384, 175, 50, "op3 对比 取交集", ORANGE))
    o.append(onode(215, 486, 175, 50, "op4 回答 + 溯源", GREEN))
    o.append(arrow(210, 336, 288, 382, RED, 2.2))
    o.append(arrow(405, 336, 318, 382, PURPLE, 2.2))
    o.append(arrow(302, 436, 302, 484, ORANGE, 2.2))
    o.append(text(120, 578, "两种进门同框：向量 + 精确，在实体层汇合求交集", 12, MUTE, "600"))
    # ---- right PEP ----
    o.append(rect(560, 184, 650, 448, "#F5FBFA", rx=16, stroke=TEAL, sw=1.3))
    o.append(text(582, 213, "② 物理执行计划(PEP)", 15, TEAL, "800"))
    o.append(text(860, 213, "实线 = 数据流　虚线 = 取数（读存储）", 11.5, MUTE, "500"))
    # operators
    o.append(onode(600, 254, 150, 44, "P1 Search 向量检索", RED, fs=12))
    o.append(onode(770, 254, 150, 44, "P3 Search IND", BLUE, fs=12.5))
    o.append(onode(600, 326, 150, 44, "P2 Lift 块→实体去重", TEAL, fs=11.5))
    o.append(onode(770, 326, 150, 44, "P4 Traverse requires", TEAL, fs=12))
    o.append(onode(685, 398, 150, 44, "P5 Intersect 交集", ORANGE, fs=12.5))
    o.append(onode(685, 470, 150, 44, "P6 Ground 取原文", GREEN, fs=12.5))
    o.append(onode(685, 542, 150, 44, "P7 Answer 溯源", NAVY, fs=12.5))
    # flow arrows
    o.append(arrow(675, 298, 675, 324, RED, 1.9))
    o.append(arrow(845, 298, 845, 324, BLUE, 1.9))
    o.append(arrow(675, 370, 730, 396, TEAL, 1.9))
    o.append(arrow(845, 370, 790, 396, TEAL, 1.9))
    o.append(arrow(760, 442, 760, 468, ORANGE, 1.9))
    o.append(arrow(760, 514, 760, 540, GREEN, 1.9))
    # stores
    o.append(scard(970, 246, 178, 46, "块向量+原文", RED, "#FBE6E2"))
    o.append(scard(970, 322, 178, 44, "实体索引", BLUE, "#EAF2FC"))
    o.append(scard(970, 394, 178, 44, "边表 / 图", TEAL, "#E4F4F2"))
    # read lines
    # 块向量 → P1 (prominent, L-route above operators)
    o.append(line(1000, 246, 1000, 232, RED, 1.8, dash="4 3"))
    o.append(line(1000, 232, 675, 232, RED, 1.8, dash="4 3"))
    o.append(arrow(675, 232, 675, 252, RED, 1.8, dash="4 3", marker="arrowo"))
    o.append(arrow(968, 338, 924, 278, BLUE, 1.6, dash="4 3"))     # 实体索引 → P3
    o.append(arrow(968, 408, 924, 348, TEAL, 1.6, dash="4 3"))     # 边表 → P4
    o.append(arrow(968, 414, 839, 488, TEAL, 1.6, dash="4 3"))     # 边表 → P6
    # 关键文字 note
    o.append(rect(966, 452, 182, 96, "#FFF4F1", rx=10, stroke=RED, sw=1.2))
    o.append(text(984, 474, "关键文字（embed→ANN）", 11.5, RED, "800"))
    for j, ln in enumerate(["细胞治疗 干细胞 免疫细胞", "产品 研究评价 临床 指导原则"]):
        o.append(text(984, 496 + j * 18, ln, 11, MUTE, "600"))
    o.append(text(984, 538, "P6 读 边表 + 块存储(原文)", 10.5, MUTE, "600"))
    o.append(text(600, 606, "同色算子读同一存储（P2 Lift、P4 读边表）· P5 纯内存 · 向量入口只在 P1 点亮",
                  11.5, MUTE, "600"))
    return svg("".join(o))


# ============================================================ EX2 EXEC
def ex2_exec():
    o = [cap("例② 逐步执行：向量命中的“细胞治疗类”与“IND 法规集”求交集（∩），落在两个集合重叠处的 7 条即为答案。")]
    # ---- Venn ----
    o.append(vcirc(360, 402, 165, TEAL))
    o.append(vcirc(560, 402, 165, BLUE))
    o.append(text(292, 214, "细胞治疗类（向量命中）", 14.5, TEAL, "800", anchor="middle"))
    o.append(text(292, 236, "约 10 条", 12.5, MUTE, "600", anchor="middle"))
    o.append(text(628, 214, "IND 申报所需", 15.5, BLUE, "800", anchor="middle"))
    o.append(text(628, 236, "共 10 条", 12.5, MUTE, "600", anchor="middle"))
    # left-only
    o.append(circle(256, 372, 25, fill=TEAL))
    o.append(text(256, 380, "3", 18, "#FFFFFF", "800", anchor="middle"))
    o.append(text(256, 430, "仅细胞治疗", 12.5, TEAL, "800", anchor="middle"))
    o.append(text(256, 448, "(属 IIT)", 11, MUTE, "600", anchor="middle"))
    # overlap (the intersect result) — highlighted
    o.append(circle(460, 386, 34, fill=ORANGE))
    o.append(text(460, 398, "7", 32, "#FFFFFF", "800", anchor="middle"))
    o.append(text(460, 446, "∩ 交集", 13, ORANGE, "800", anchor="middle"))
    # right-only
    o.append(circle(664, 372, 25, fill=BLUE))
    o.append(text(664, 380, "3", 18, "#FFFFFF", "800", anchor="middle"))
    o.append(text(664, 430, "仅 IND", 12.5, BLUE, "800", anchor="middle"))
    # connector
    o.append(arrow(494, 372, 742, 300, ORANGE, 2, dash="5 4", marker="arrowo"))
    o.append(text(560, 300, "取交集", 12, ORANGE, "800"))
    # ---- result card ----
    o.append(rlist_card(742, 236, 456, 300, "P5 结果：细胞治疗类 ∩ IND = 7 条",
                        ["人源干细胞非临床", "人源干细胞药学", "人源性干细胞临床试验",
                         "细胞治疗临床药理学", "细胞治疗研究与评价", "免疫细胞药学",
                         "免疫细胞临床试验"], ORANGE))
    # ---- answer band ----
    o.append(rect(70, 560, 1140, 58, "#0E2E52", rx=12))
    o.append(rect(70, 560, 6, 58, GREEN, rx=3))
    o.append(text(92, 584, "P6 Ground 只取这 7 条原文 → P7 回答：", 14, "#8FD3FF", "800"))
    o.append(text(92, 606, "“与细胞治疗相关、且属于 IND 申报要求的法规有 7 部……”，各附 fullname 出处。向量进门，图求关系，实体层汇合。",
                  12.5, "#DCEBFA", "600"))
    return svg("".join(o))


# ============================================================ ICONS
def ico(name, cx, cy, r, c):
    if name == "search":
        return (circle(cx - r * .15, cy - r * .15, r * .52, fill="none", stroke=c, sw=3)
                + line(cx + r * .22, cy + r * .22, cx + r * .62, cy + r * .62, c, 3.4))
    if name == "relate":
        return (circle(cx - r * .48, cy - r * .22, r * .24, fill=c)
                + circle(cx + r * .48, cy + r * .22, r * .24, fill=c)
                + line(cx - r * .3, cy - r * .14, cx + r * .3, cy + r * .14, c, 3))
    if name == "filter":
        return (f'<path d="M{cx-r*.6},{cy-r*.5} L{cx+r*.6},{cy-r*.5} L{cx+r*.16},{cy+r*.04} '
                f'L{cx+r*.16},{cy+r*.55} L{cx-r*.16},{cy+r*.34} L{cx-r*.16},{cy+r*.04} Z" fill="{c}"/>')
    if name == "compare":
        return (circle(cx - r * .26, cy, r * .46, fill=c, opacity=.45)
                + circle(cx + r * .26, cy, r * .46, fill=c, opacity=.45))
    if name == "sum":
        return "".join(rect(cx - r * .55, cy - r * .45 + i * r * .42, r * (1.1 - i * .3), 6, c, rx=3) for i in range(3))
    if name == "verify":
        return (f'<path d="M{cx},{cy-r*.6} L{cx+r*.5},{cy-r*.32} L{cx+r*.5},{cy+r*.1} '
                f'Q{cx+r*.5},{cy+r*.48} {cx},{cy+r*.62} Q{cx-r*.5},{cy+r*.48} {cx-r*.5},{cy+r*.1} '
                f'L{cx-r*.5},{cy-r*.32} Z" fill="{c}"/>'
                f'<path d="M{cx-r*.22},{cy+r*.02} L{cx-r*.04},{cy+r*.22} L{cx+r*.28},{cy-r*.18}" '
                f'stroke="#fff" stroke-width="2.6" fill="none" stroke-linecap="round"/>')
    if name == "answer":
        return (rect(cx - r * .58, cy - r * .5, r * 1.16, r * .8, c, rx=6)
                + f'<path d="M{cx-r*.25},{cy+r*.28} L{cx-r*.05},{cy+r*.55} L{cx+r*.12},{cy+r*.28} Z" fill="{c}"/>')
    if name == "dag":
        return (circle(cx, cy - r * .45, r * .18, fill=c) + circle(cx - r * .45, cy + r * .4, r * .18, fill=c)
                + circle(cx + r * .45, cy + r * .4, r * .18, fill=c)
                + line(cx - r * .1, cy - r * .3, cx - r * .38, cy + r * .25, c, 2.4)
                + line(cx + r * .1, cy - r * .3, cx + r * .38, cy + r * .25, c, 2.4))
    if name == "layers":
        return (f'<path d="M{cx},{cy-r*.5} L{cx+r*.6},{cy-r*.2} L{cx},{cy+r*.1} L{cx-r*.6},{cy-r*.2} Z" fill="{c}" opacity="0.5"/>'
                f'<path d="M{cx},{cy-r*.02} L{cx+r*.6},{cy+r*.28} L{cx},{cy+r*.58} L{cx-r*.6},{cy+r*.28} Z" fill="{c}"/>')
    if name == "split":
        return (rect(cx - r * .55, cy - r * .42, r * .45, r * .84, c, rx=4, opacity=.5)
                + rect(cx + r * .1, cy - r * .42, r * .45, r * .84, c, rx=4))
    if name == "robot":
        return (rect(cx - r * .45, cy - r * .3, r * .9, r * .68, c, rx=8)
                + circle(cx - r * .17, cy + r * .04, r * .1, fill="#fff") + circle(cx + r * .17, cy + r * .04, r * .1, fill="#fff")
                + line(cx, cy - r * .3, cx, cy - r * .55, c, 2.4) + circle(cx, cy - r * .6, r * .09, fill=c))
    if name == "gear":
        teeth = "".join(f'<rect x="{cx-3}" y="{cy-r*.62}" width="6" height="{r*.26}" fill="{c}" '
                        f'transform="rotate({k*60} {cx} {cy})"/>' for k in range(6))
        return teeth + circle(cx, cy, r * .4, fill=c) + circle(cx, cy, r * .16, fill="#fff")
    if name == "doclink":
        return (rect(cx - r * .4, cy - r * .55, r * .8, r * 1.1, c, rx=4)
                + line(cx - r * .2, cy - r * .25, cx + r * .2, cy - r * .25, "#fff", 2.4)
                + line(cx - r * .2, cy, cx + r * .2, cy, "#fff", 2.4)
                + f'<path d="M{cx-r*.12},{cy+r*.28} L{cx},{cy+r*.42} L{cx+r*.22},{cy+r*.16}" '
                f'stroke="#fff" stroke-width="2.6" fill="none" stroke-linecap="round"/>')
    if name == "key":
        return (circle(cx - r * .25, cy - r * .05, r * .3, fill="none", stroke=c, sw=3)
                + line(cx - r * .02, cy + r * .12, cx + r * .5, cy + r * .55, c, 3)
                + line(cx + r * .3, cy + r * .35, cx + r * .5, cy + r * .15, c, 3))
    return ""


def disc(cx, cy, r, soft):
    return circle(cx, cy, r, fill=soft)


def chip(x, y, s, c, sz=11):
    w = len(s) * 7.4 + 18
    return (rect(x, y, w, 26, PANEL, rx=6, stroke=c, sw=1.2)
            + text(x + w / 2, y + 17, s, sz, c, "700", anchor="middle", ff=MONO), w)


SOFT = {PURPLE: PURPLE_SOFT, BLUE: BLUE_SOFT, TEAL: TEAL_SOFT, ORANGE: ORANGE_SOFT,
        GREEN: GREEN_SOFT, NAVY: "#E1EAF4", RED: "#FBE6E2"}


# ============================================================ PHILOSOPHY
def philosophy():
    o = [cap("把检索从“黑箱猜”变成“看得见的图上计算”：大模型编译可见步骤，在两层图上执行，条条可溯源。")]
    items = [
        ("dag", "可见的算子图 SQG", "大模型编译查询步骤，每步一句人话，可排查。", PURPLE),
        ("layers", "两层图", "实体层管关系，块层管原文与向量入口。", BLUE),
        ("split", "逻辑与执行分离", "大模型只说“想干什么”，执行器负责“怎么做”。", TEAL),
        ("robot", "关系只用 LLM 建", "便宜手段只提名候选，判定权全给 LLM。", ORANGE),
        ("gear", "优化后再执行", "下推·并行·惰性取原文·缓存，跑得快又省。", GREEN),
        ("doclink", "可溯源", "每条答案带 fullname 出处，执行后可回填排查。", NAVY),
    ]
    x0, y0, cw, ch, gx, gy = 70, 184, 366, 150, 21, 20
    for i, (ic, t, d, c) in enumerate(items):
        col, row = i % 3, i // 3
        x, y = x0 + col * (cw + gx), y0 + row * (ch + gy)
        o.append(card(x, y, cw, ch, accent=c))
        o.append(disc(x + 52, y + 52, 27, SOFT[c]))
        o.append(ico(ic, x + 52, y + 52, 20, c))
        o.append(text(x + 92, y + 48, t, 17, INK, "800"))
        for j, ln in enumerate(wrapw(d, 28)):
            o.append(text(x + 28, y + 96 + j * 20, ln, 13, MUTE, "500"))
    return svg("".join(o))


# ============================================================ LOGICAL OPS
def logical_ops():
    o = [cap("大模型只能从这一小把“意图级”算子里挑，一句人话能说清；固定目录，不让 LLM 造新算子。")]
    items = [
        ("search", "检索 Retrieve", "找出与描述相关的内容/对象", BLUE),
        ("relate", "关联 Relate", "从已有结果顺关系找相关对象", TEAL),
        ("filter", "筛选 Filter", "按条件留一部分", GREEN),
        ("compare", "对比 Compare", "比两组异同 / 找各自独有", ORANGE),
        ("sum", "汇总 Summarize", "概括归纳一堆内容", PURPLE),
        ("verify", "校验 Verify", "检查全不全、对不对（可回环）", RED),
        ("answer", "回答 Answer", "综合成答案并标出处", NAVY),
    ]
    cw, ch, gx, gy = 270, 196, 20, 22
    for i, (ic, t, d, c) in enumerate(items):
        if i < 4:
            x = 70 + i * (cw + gx); y = 182
        else:
            x = 215 + (i - 4) * (cw + gx); y = 182 + ch + gy
        o.append(card(x, y, cw, ch, accent=c))
        o.append(disc(x + cw / 2, y + 60, 34, SOFT[c]))
        o.append(ico(ic, x + cw / 2, y + 60, 25, c))
        o.append(text(x + cw / 2, y + 122, t, 18, INK, "800", anchor="middle"))
        for j, ln in enumerate(wrapw(d, 15)):
            o.append(text(x + cw / 2, y + 150 + j * 20, ln, 13, MUTE, "500", anchor="middle"))
    return svg("".join(o))


# ============================================================ PHYSICAL MAP
def physical_map():
    o = [cap("检索侧塌缩成一个 Search 算子（=一次 AI Search 调用）；只自建 AI Search 不做的：图关系、集合、LLM、校验。")]
    # left: physical catalog
    o.append(card(70, 182, 380, 452, accent=BLUE))
    o.append(text(94, 214, "物理算子（执行零件）", 16, INK, "800"))
    o.append(text(94, 234, "大模型不可见，由优化器编排", 12, MUTE, "500"))
    cat = [("① Search＝一次 AI Search 调用", "向量·关键词·别名·过滤·重排·排序·阈值", BLUE),
           ("图导航（自建）", "Lift · Ground · Traverse", TEAL),
           ("集合（自建·内存）", "Intersect · Diff · Union · Dedup", ORANGE),
           ("LLM 加工（Azure OpenAI）", "Summarize · Extract · Generate", PURPLE),
           ("校验控制（自建）", "SetCheck · Provenance · Abstain", RED)]
    for i, (t, d, c) in enumerate(cat):
        y = 258 + i * 74
        o.append(rect(94, y, 332, 62, "#F5F8FD", rx=8, stroke="#DEE7F2", sw=1))
        o.append(rect(94, y, 5, 62, c, rx=2))
        o.append(text(112, y + 26, t, 13, c, "800"))
        o.append(text(112, y + 46, d, 10.5, MUTE, "600", ff=MONO))
    # right: mapping
    o.append(text(478, 210, "逻辑算子  →  物理子计划", 15, INK, "800"))
    rows = [
        ("检索", BLUE, [("Search", BLUE), ("Traverse", TEAL), ("｜Lift", MUTE)]),
        ("关联", TEAL, [("Lift", TEAL), ("Traverse", TEAL), ("Ground", GREEN)]),
        ("筛选", GREEN, [("Search($filter)", GREEN), ("｜LLM_Judge", MUTE)]),
        ("对比", ORANGE, [("Diff", ORANGE), ("Intersect", ORANGE), ("Union", ORANGE)]),
        ("汇总", PURPLE, [("Ground", GREEN), ("LLM_Summarize", PURPLE)]),
        ("校验", RED, [("SetCheck", RED), ("Provenance", RED), ("Abstain", RED)]),
        ("回答", NAVY, [("Ground", GREEN), ("LLM_Generate", NAVY)]),
    ]
    for i, (lop, lc, chips) in enumerate(rows):
        y = 232 + i * 56
        o.append(pill(478, y, 70, 34, lc, lop, 14, "#FFFFFF", "800"))
        o.append(arrow(552, y + 17, 574, y + 17, MUTE, 2))
        cx = 580
        for (s, cc) in chips:
            frag, w = chip(cx, y + 4, s, cc)
            o.append(frag)
            cx += w + 10
            if cc == chips[-1][1] and s == chips[-1][0]:
                continue
            o.append(text(cx - 6, y + 21, "›", 12, FAINT, "700"))
    o.append(text(478, 630, "例：检索(精确)=Search(名)→Traverse ；检索(语义)=Search(向量)→Lift（同算子两种展开）",
                  11.5, MUTE, "600"))
    return svg("".join(o))


# ============================================================ OPTIMIZER
def optimizer():
    o = [cap("优化器把大模型写的逻辑图，编译成又对又快的可执行 DAG：校验 → 绑定 → 优化 → 编排执行。")]
    # input SQG (rough)
    o.append(card(70, 190, 250, 250, accent=PURPLE))
    o.append(text(94, 222, "输入：SQG（逻辑）", 14.5, PURPLE, "800"))
    for (nx, ny) in [(150, 270), (250, 270), (200, 340), (200, 400)]:
        o.append(rect(nx - 44, ny - 16, 88, 32, PANEL, rx=8, stroke=PURPLE, sw=1.3))
    o.append(arrow(150, 286, 190, 326, PURPLE, 1.8))
    o.append(arrow(250, 286, 212, 326, PURPLE, 1.8))
    o.append(arrow(200, 356, 200, 386, PURPLE, 1.8))
    o.append(text(196, 276, "op", 11, MUTE, "700", anchor="middle"))
    o.append(arrow(322, 315, 356, 315, MUTE, 2.6))
    # optimizer box (4 steps)
    o.append(card(360, 190, 300, 250, accent=ORANGE))
    o.append(text(384, 222, "② 优化器", 15, ORANGE, "800"))
    steps = [("verify", "校验：无环/类型/参数", BLUE),
             ("bind" if False else "gear", "绑定：逻辑→物理算子", TEAL),
             ("gear", "优化：下推·并行·惰性·缓存", GREEN),
             ("order", "编排成可执行 DAG", NAVY)]
    for i, (icn, t, c) in enumerate(steps):
        y = 244 + i * 48
        o.append(rect(384, y, 252, 40, "#FFF7EF", rx=8, stroke="#F0DFC7", sw=1))
        o.append(disc(406, y + 20, 15, SOFT.get(c, "#EEE")))
        o.append(ico("verify" if i == 0 else ("gear" if i in (1, 2) else "order"), 406, y + 20, 11, c))
        o.append(text(430, y + 25, t, 13, INK, "700"))
    o.append(arrow(662, 315, 696, 315, MUTE, 2.6))
    # output PEP (clean)
    o.append(card(700, 190, 250, 250, accent=TEAL))
    o.append(text(724, 222, "输出：PEP（物理）", 14.5, TEAL, "800"))
    for i, (nx, ny) in enumerate([(760, 268), (860, 268), (760, 330), (860, 330), (810, 392)]):
        o.append(rect(nx - 42, ny - 15, 84, 30, PANEL, rx=7, stroke=TEAL, sw=1.3))
        o.append(text(nx, ny + 4, f"P{i+1}", 11.5, TEAL, "800", anchor="middle"))
    o.append(arrow(760, 283, 760, 315, TEAL, 1.6))
    o.append(arrow(860, 283, 860, 315, TEAL, 1.6))
    o.append(arrow(770, 345, 800, 377, TEAL, 1.6))
    o.append(arrow(850, 345, 820, 377, TEAL, 1.6))
    # speed badge
    o.append(pill(985, 300, 150, 46, GREEN, "更快 · 更省", 16, "#FFFFFF", "800"))
    o.append(text(1060, 360, "同一逻辑图", 12, MUTE, "600", anchor="middle"))
    o.append(text(1060, 378, "跑得又快又省", 12, MUTE, "600", anchor="middle"))
    # optimization chips
    o.append(text(94, 476, "四类优化：", 14, INK, "800"))
    techs = [("谓词下推", "条件压进检索早筛"), ("独立分支并行", "两路同时跑"),
             ("惰性取原文", "中间只用 id"), ("公共子表达式复用", "同检索只算一次")]
    x = 210
    for (t, d) in techs:
        w = 250
        o.append(card(x, 460, w, 84, accent=GREEN, shadow=True))
        o.append(disc(x + 30, 490, 16, GREEN_SOFT))
        o.append(ico("gear", x + 30, 490, 12, GREEN))
        o.append(text(x + 56, 488, t, 14, INK, "800"))
        o.append(text(x + 56, 512, d, 12, MUTE, "600"))
        x += w + 12
    return svg("".join(o))


# ============================================================ COMPARE
def compare():
    o = [cap("同一套算子与执行器，按“入口是精确名还是语义描述”自动选择是否查向量。")]
    panels = [
        ("例① 精确入口", "key", BLUE, "IND 要求、NDA 不要求的法规",
         "diff", ["进门：Search（精确名，实体索引）", "查向量库：否", "关键文字：直接用名字 IND/NDA",
                  "集合运算：Diff（差集）→ 8 条"]),
        ("例② 向量入口", "search", RED, "细胞治疗相关且属于 IND 的法规",
         "inter", ["进门：Search（向量，块向量库 ANN）", "查向量库：是（P1）", "关键文字：“细胞治疗 干细胞…”",
                   "集合运算：Intersect（交集）→ 7 条"]),
    ]
    for i, (title, icn, c, q, vk, facts) in enumerate(panels):
        x = 70 + i * 590
        o.append(card(x, 182, 550, 380, accent=c))
        o.append(disc(x + 44, 222, 22, SOFT[c]))
        o.append(ico(icn, x + 44, 222, 16, c))
        o.append(text(x + 78, 214, title, 19, INK, "800"))
        o.append(text(x + 78, 238, q, 12.5, MUTE, "600"))
        # mini venn
        vy = 340
        if vk == "diff":
            o.append(vcirc(x + 150, vy, 78, BLUE))
            o.append(vcirc(x + 240, vy, 78, TEAL))
            o.append(circle(x + 110, vy - 16, 20, fill=BLUE))
            o.append(text(x + 110, vy - 9, "8", 20, "#FFFFFF", "800", anchor="middle"))
            o.append(text(x + 195, vy + 100, "差集 Diff", 12.5, MUTE, "700", anchor="middle"))
        else:
            o.append(vcirc(x + 150, vy, 78, TEAL))
            o.append(vcirc(x + 240, vy, 78, BLUE))
            o.append(circle(x + 195, vy - 6, 22, fill=ORANGE))
            o.append(text(x + 195, vy + 1, "7", 20, "#FFFFFF", "800", anchor="middle"))
            o.append(text(x + 195, vy + 100, "交集 Intersect", 12.5, MUTE, "700", anchor="middle"))
        # facts
        fy = 268
        for f in facts:
            o.append(circle(x + 348, fy - 4, 3, fill=c))
            for j, ln in enumerate(wrapw(f, 20)):
                o.append(text(x + 360, fy + j * 18, ln, 12.5, INK if j == 0 else MUTE, "600"))
            fy += 18 * len(wrapw(f, 20)) + 12
    o.append(rect(70, 578, 1140, 44, "#0E2E52", rx=10))
    o.append(text(92, 605, "共同优化：惰性取原文 · 独立分支并行 · 中间只用 id · 逐条 fullname 溯源",
                  13.5, "#DCEBFA", "700"))
    return svg("".join(o))


# ============================================================ CLOSING
def closing():
    o = [cap("一句话：向量负责“进门找相关”，实体层关系负责“找全找准”，SQG 让思路看得见，fullname 负责对齐与溯源。")]
    stages = [("search", "向量进门", "命中相关块", RED),
              ("relate", "图找全找准", "沿关系精确聚合", TEAL),
              ("dag", "SQG 可见", "每步可排查", PURPLE),
              ("doclink", "fullname 溯源", "条条有出处", GREEN)]
    x0, cw, gx = 90, 250, 40
    for i, (icn, t, d, c) in enumerate(stages):
        x = x0 + i * (cw + gx)
        o.append(card(x, 190, cw, 130, accent=c))
        o.append(disc(x + cw / 2, 232, 30, SOFT[c]))
        o.append(ico(icn, x + cw / 2, 232, 22, c))
        o.append(text(x + cw / 2, 284, t, 16.5, INK, "800", anchor="middle"))
        o.append(text(x + cw / 2, 306, d, 12.5, MUTE, "600", anchor="middle"))
        if i < 3:
            o.append(arrow(x + cw + 4, 255, x + cw + gx - 4, 255, MUTE, 2.6))
    # positioning
    pos = [("对比裸向量 RAG", "不止取 Top-K，而是编译出可见步骤、在两层图上按意图走：能多跳、能列全、能溯源、能排查。", BLUE),
           ("对比 OG-RAG（超图+集合覆盖）", "我们用两层图 + 大模型编译的算子 DAG + 优化器/执行器，把“怎么查”显式化、可视化，贴合文档天然层级。", TEAL)]
    for i, (t, d, c) in enumerate(pos):
        x = 70 + i * 590
        o.append(card(x, 348, 550, 150, accent=c))
        o.append(text(x + 26, 386, t, 17, INK, "800"))
        for j, ln in enumerate(wrapw(d, 34)):
            o.append(text(x + 26, 418 + j * 22, ln, 13.5, MUTE, "600"))
    o.append(rect(70, 520, 1140, 54, "#0E2E52", rx=12))
    o.append(rect(70, 520, 6, 54, ORANGE, rx=3))
    o.append(text(92, 552, "落地节奏：先小本体 + 固定算子子集跑通 → 再逐步加优化器与算子；评估看 计划正确率 / 覆盖率 / 漂移率 / 溯源率。",
                  13.5, "#DCEBFA", "700"))
    return svg("".join(o))


# ============================================================ ALGO helpers
def iocard(x, y, w, h, label, accent, lines):
    o = card(x, y, w, h, accent=accent)
    o += pill(x + 18, y + 16, 76, 26, accent, label, 13, "#FFFFFF", "800")
    yy = y + 62
    for ln in lines:
        col = MUTE if (ln.startswith("·") or ln.startswith("(") or ln.startswith("（")) else INK
        for L in wrapw(ln, int((w - 40) / 7.6)):
            o += text(x + 20, yy, L, 13, col, "600")
            yy += 20
        yy += 4
    return o


def steps_list(x, y, items, accent, w):
    o = ""
    yy = y
    for i, it in enumerate(items):
        o += circle(x + 12, yy - 4, 12, fill=accent)
        o += text(x + 12, yy + 1, str(i + 1), 12, "#FFFFFF", "800", anchor="middle")
        wr = wrapw(it, int((w - 44) / 7.7))
        for j, L in enumerate(wr):
            o += text(x + 34, yy + j * 19, L, 13.2, INK, "600")
        yy += 19 * len(wr) + 14
    return o


def _exband(o, lines, title="具体例子"):
    o.append(rect(70, 506, 1140, 112, "#0E2E52", rx=12))
    o.append(rect(70, 506, 6, 112, ORANGE, rx=3))
    o.append(text(92, 534, title, 13.5, "#8FD3FF", "800"))
    yy = 560
    for ln in lines:
        o.append(text(96, yy, ln, 12.8, "#DCEBFA", "600"))
        yy += 22


def _algo(capt, inp, steps, out, ex, cin=BLUE, cout=GREEN, cmid=PURPLE):
    o = [cap(capt)]
    o.append(iocard(70, 186, 268, 300, "输入", cin, inp))
    o.append(arrow(340, 336, 370, 336, MUTE, 2.6))
    o.append(card(372, 186, 472, 300, accent=cmid))
    o.append(pill(392, 202, 96, 26, cmid, "算法过程", 12.5, "#FFFFFF", "800"))
    o.append(steps_list(394, 258, steps, cmid, 452))
    o.append(arrow(846, 336, 876, 336, MUTE, 2.6))
    o.append(iocard(878, 186, 332, 300, "输出", cout, out))
    _exband(o, ex)
    return svg("".join(o))


# ============================================================ ALGO OVERVIEW
def algo_overview():
    o = [cap("物理算子是执行器真正会跑的原语。下面逐个讲解其算法、输入 / 输出与计算过程。")]
    groups = [
        ("Search（AI Search）", BLUE, ["向量 / 关键词 / 别名", "过滤 $filter · 语义重排", "top / 排序 / 阈值 —— 一次调用"]),
        ("图导航（自建）", TEAL, ["Lift 块 → 实体", "Ground 实体 → 块", "Traverse 带权扩散 / 多跳"]),
        ("集合（自建·内存）", ORANGE, ["Intersect / Diff / Union", "Dedup 去重", "跨结果集合并"]),
        ("LLM 加工", PURPLE, ["Summarize / Extract", "Compare / Generate", "Judge"]),
        ("校验控制（自建）", RED, ["SetCheck 完整性", "ProvenanceCheck 溯源", "Abstain 低置信兜底"]),
    ]
    x0, y0, cw, ch, gx, gy = 70, 184, 366, 150, 21, 20
    for i, (t, c, ops) in enumerate(groups):
        col, row = i % 3, i // 3
        x, y = x0 + col * (cw + gx), y0 + row * (ch + gy)
        o.append(card(x, y, cw, ch, accent=c))
        o.append(text(x + 24, y + 38, t, 17, INK, "800"))
        o.append(line(x + 24, y + 52, x + cw - 24, y + 52, LINE, 1))
        for j, op in enumerate(ops):
            o.append(circle(x + 30, y + 76 + j * 26, 3, fill=c))
            o.append(text(x + 42, y + 80 + j * 26, op, 13.5, MUTE, "600"))
    o.append(text(70, 546, "原则：AI Search 做得好的（检索/过滤/重排/排序）塌缩成一个 Search 算子；只自建它不做的四类。",
                  13, MUTE, "700"))
    return svg("".join(o))


# ============================================================ ALGO: Search (AI Search)
def algo_search():
    o = [cap("Search＝一次 AI Search 调用：向量 / 关键词 / 别名 / 过滤 / 语义重排 / 排序 全靠参数，一趟搞定检索侧。")]
    o.append(iocard(70, 186, 240, 300, "输入", BLUE,
                    ["查询（名字或描述）", "如 “IND” 或 “细胞治疗相关的法规”", "+ $filter / $top / 语义开关"]))
    o.append(arrow(312, 336, 342, 336, MUTE, 2.6))
    o.append(card(344, 186, 520, 300, accent=BLUE))
    o.append(pill(364, 202, 150, 26, BLUE, "一次 /docs/search", 11.5, "#FFFFFF", "800"))
    params = [("search + vectorQueries", "向量 / 混合 / 关键词检索", TEAL),
              ("+ Synonym Map", "别名 / 缩写归一（GCP→…）", TEAL),
              ("$filter", "结构化过滤 / 枚举（可与向量组合、下推）", GREEN),
              ("queryType=semantic", "内置 Semantic Ranker 重排 Top-50", ORANGE),
              ("$top / $orderby / threshold", "取前 K / 排序 / 低分排除", PURPLE)]
    for i, (p, d, c) in enumerate(params):
        y = 240 + i * 48
        o.append(rect(364, y, 480, 40, "#F5F8FD", rx=8, stroke="#DEE7F2", sw=1))
        o.append(rect(364, y, 5, 40, c, rx=2))
        o.append(text(380, y + 18, p, 12, c, "800", ff=MONO))
        o.append(text(380, y + 34, d, 10.5, MUTE, "600"))
    o.append(arrow(866, 336, 896, 336, MUTE, 2.6))
    o.append(iocard(898, 186, 312, 300, "输出", GREEN,
                    ["命中的实体 / 块 + 分数", "精确名 → 实体（走 Traverse）", "语义描述 → 块（走 Lift）"]))
    _exband(o, ["旧设计的 Resolve / Seed / ScanEntities / FilterField / Rerank / TopK / SortByFullname / Threshold",
                "全是同一个请求上的字段 → 合并成一个 Search 算子；打实体索引还是块索引，由参数决定。"])
    return svg("".join(o))


# ============================================================ ALGO: Lift / Ground
def algo_lift_ground():
    o = [cap("Lift / Ground：在“块 ↔ 实体”之间转换，走的是 evidence 边。Lift 抬升到实体，Ground 落回原文块。")]
    o.append(card(70, 186, 555, 300, accent=TEAL))
    o.append(pill(90, 204, 90, 26, TEAL, "Lift", 13, "#FFFFFF", "800"))
    o.append(text(190, 222, "块 → 它所属 / 佐证的实体（沿 evidence 反向）", 13, INK, "700"))
    o.append(node(110, 260, 150, 40, "块 GCP·总则", TEAL_SOFT, TEAL, tsize=12))
    o.append(arrow(262, 280, 360, 280, TEAL, 2.2, dash="4 3", marker="arrowt"))
    o.append(text(311, 272, "evidence 反", 10.5, MUTE, "700", anchor="middle"))
    o.append(node(362, 260, 150, 40, "Reg:GCP", "#E9F6F4", TEAL, tsize=13))
    o.append(text(90, 340, "步骤：对每个块沿 evidence 反向找实体 → 去重 → 得到实体集。", 12.8, MUTE, "600"))
    o.append(text(90, 366, "用途：Search（向量）命中块后，抬到实体层才能走结构关系（requires…）。", 12.8, MUTE, "600"))
    o.append(text(90, 392, "多个块可能佐证同一实体 → 需 Dedup。", 12.8, MUTE, "600"))

    o.append(card(655, 186, 555, 300, accent=GREEN))
    o.append(pill(675, 204, 96, 26, GREEN, "Ground", 13, "#FFFFFF", "800"))
    o.append(text(785, 222, "实体 → 它的证据块（沿 evidence 正向）", 13, INK, "700"))
    o.append(node(680, 260, 150, 40, "Reg:GCP", "#E3F4EA", GREEN, tsize=13))
    o.append(arrow(832, 268, 930, 258, GREEN, 2, marker="arrowg"))
    o.append(arrow(832, 288, 930, 300, GREEN, 2, marker="arrowg"))
    o.append(node(932, 240, 150, 36, "块 GCP·总则", GREEN_SOFT, GREEN, tsize=11.5))
    o.append(node(932, 286, 150, 36, "块 GCP·定义", GREEN_SOFT, GREEN, tsize=11.5))
    o.append(text(675, 356, "步骤：对每个实体沿 evidence 正向取其证据块。", 12.8, MUTE, "600"))
    o.append(text(675, 382, "用途：最终 P6 只对幸存实体 Ground 取原文（惰性）。", 12.8, MUTE, "600"))
    _exband(o, ["Lift：块(GCP·总则) → Reg:GCP；Ground：Reg:GCP → [块(总则), 块(定义)]。",
                "数据源：边表（evidence 边）+ 块存储；轻量的图/存储查找。"])
    return svg("".join(o))


# ============================================================ ALGO: Traverse
def algo_traverse():
    o = [cap("Traverse（带权扩散 Spreading Activation）：从起点沿类型化边扩散，带权重衰减、阈值与防环。图导航的核心。")]
    o.append(iocard(70, 186, 250, 300, "输入", TEAL, ["起点节点集 S0", "edge_type（如 requires）",
                                                    "方向 dir（out / in）", "max_hops、阈值 τ、衰减 γ"]))
    o.append(arrow(322, 336, 352, 336, MUTE, 2.6))
    o.append(card(354, 186, 510, 300, accent=TEAL))
    o.append(pill(374, 202, 96, 26, TEAL, "算法过程", 12.5, "#FFFFFF", "800"))
    # spreading graph
    o.append(node(392, 300, 96, 40, "IND", BLUE_SOFT, BLUE, tsize=13))
    o.append(text(440, 356, "act=1.0", 11, BLUE, "800", anchor="middle"))
    o.append(arrow(490, 308, 560, 278, TEAL, 2))
    o.append(arrow(490, 332, 560, 362, TEAL, 2))
    o.append(text(528, 288, "×w·γ", 9.5, MUTE, "700"))
    o.append(node(562, 258, 110, 38, "GCP", TEAL_SOFT, TEAL, tsize=12))
    o.append(text(617, 310, "act=.54", 10.5, TEAL, "800", anchor="middle"))
    o.append(node(562, 344, 110, 38, "药品管理法", TEAL_SOFT, TEAL, tsize=11))
    o.append(text(617, 396, "act=.54", 10.5, TEAL, "800", anchor="middle"))
    o.append(arrow(674, 274, 736, 262, "#C6D2E0", 1.8, dash="3 3"))
    o.append(node(738, 244, 96, 34, "下一跳", "#F0F4F9", "#9FB0C2", tsize=11))
    o.append(text(786, 300, "act=.29 < τ", 10.5, RED, "800", anchor="middle"))
    o.append(text(738, 330, "剪枝停止", 10.5, RED, "700"))
    o.append(text(374, 458, "① act(seed)=1 ② 沿边 BFS：act(n)=act(cur)×w×γ ③ act<τ 或超跳数则停，visited 防环",
                  11.2, INK, "600"))
    o.append(arrow(866, 336, 896, 336, MUTE, 2.6))
    o.append(iocard(898, 186, 312, 300, "输出", GREEN, ["到达节点集 + 激活分", "按 act 排序 / 取阈值以上", "= 该起点“关系可达”的对象"]))
    _exband(o, ["act(d) = max_path  sim(seed) × Π w(e) × γ^hops   （γ 衰减，τ 阈值，visited 防环）",
                "例：IND 沿 requires 正向 1 跳 → GCP：act = 1×0.9×0.6 = 0.54（> τ 保留）。复杂度受跳数/阈值约束。"])
    return svg("".join(o))


# ============================================================ ALGO: 集合运算
def algo_setops():
    o = [cap("集合运算（Intersect / Diff / Union / Dedup）：对实体 id 集合做哈希集合运算，纯内存、确定性、不读存储。")]
    # Venn
    o.append(vcirc(300, 350, 120, BLUE))
    o.append(vcirc(430, 350, 120, TEAL))
    o.append(text(240, 250, "A", 20, BLUE, "800", anchor="middle"))
    o.append(text(490, 250, "B", 20, TEAL, "800", anchor="middle"))
    o.append(text(255, 356, "A−B", 13, BLUE, "800", anchor="middle"))
    o.append(text(365, 356, "A∩B", 13, "#2A3A4A", "800", anchor="middle"))
    o.append(text(475, 356, "B−A", 13, TEAL, "800", anchor="middle"))
    # ops explained
    ops = [("Intersect  A∩B", "两边都有 → 交集（对比“共同”）", ORANGE),
           ("Diff  A−B", "A 有 B 没有 → 差集（对比“独有”）", BLUE),
           ("Union  A∪B", "任一有 → 并集（合并）", TEAL),
           ("Dedup", "按 key（fullname/实体id）去重，保留一个", GREEN)]
    for i, (t, d, c) in enumerate(ops):
        y = 200 + i * 74
        o.append(card(620, y, 590, 62, accent=c))
        o.append(text(644, y + 26, t, 15, INK, "800", ff=MONO))
        o.append(text(644, y + 48, d, 12.8, MUTE, "600"))
    _exband(o, ["实现：用哈希集合（set），Intersect/Diff/Union 均 ≈ O(|A|+|B|)；纯内存不碰存储。",
                "例①用 Diff（IND−NDA=8）；例②用 Intersect（细胞治疗∩IND=7）。"])
    return svg("".join(o))


# ============================================================ ALGO: Filter
def algo_filter():
    o = [cap("Filter（筛选）：从结果集里按条件留一部分。分两种——结构化字段过滤，或语义条件过滤。")]
    o.append(card(70, 186, 555, 300, accent=BLUE))
    o.append(pill(90, 204, 130, 26, BLUE, "FilterField", 12.5, "#FFFFFF", "800"))
    o.append(text(230, 222, "结构化条件（快、确定）", 13, INK, "700"))
    o.append(text(90, 262, "对每个元素查字段：status / type / category …", 12.8, MUTE, "600"))
    o.append(text(90, 288, "满足即保留；可下推进索引查询（早筛）。", 12.8, MUTE, "600"))
    o.append(rect(90, 312, 515, 44, "#F4F8FD", rx=8, stroke="#DEE7F2", sw=1))
    o.append(text(104, 340, "例：筛“现行有效” → status == 现行；O(n) 字段比较。", 12.5, BLUE, "700", ff=MONO))
    o.append(text(90, 400, "不调 LLM、不做向量——只查已存的结构化属性。", 12.5, MUTE, "600"))

    o.append(card(655, 186, 555, 300, accent=PURPLE))
    o.append(pill(675, 204, 150, 26, PURPLE, "FilterSemantic", 12, "#FFFFFF", "800"))
    o.append(text(835, 222, "语义条件（灵活、较贵）", 13, INK, "700"))
    o.append(text(675, 262, "对每个元素判断是否满足语义条件：", 12.8, MUTE, "600"))
    o.append(text(675, 288, "① 向量相似度 > τ，或 ② 小 LLM 判 yes/no。", 12.8, MUTE, "600"))
    o.append(rect(675, 312, 515, 44, "#F7F4FC", rx=8, stroke="#E3DAF3", sw=1))
    o.append(text(689, 340, "例：筛“与细胞治疗相关” → cos>τ 或 LLM 判定。", 12.5, PURPLE, "700", ff=MONO))
    o.append(text(675, 400, "能用字段就用字段；字段表达不了才用语义。", 12.5, MUTE, "600"))
    _exband(o, ["优化器优先把结构化条件“下推”进 Seed/索引查询，早筛少召回噪声。",
                "语义过滤放在候选变小之后做，控制成本。"])
    return svg("".join(o))


# ============================================================ ALGO: Rerank
def algo_rerank():
    o = [cap("Rerank（交叉编码精排）：对候选逐一与问题“联合编码”打分再排序，最擅长区分近似法规名。")]
    o.append(iocard(70, 186, 260, 300, "输入", BLUE, ["问题 query", "候选集 Top-N（来自混合检索）", "如 20 条相近法规块"]))
    o.append(arrow(332, 336, 362, 336, MUTE, 2.6))
    o.append(card(364, 186, 500, 300, accent=GREEN))
    o.append(pill(384, 202, 96, 26, GREEN, "算法过程", 12.5, "#FFFFFF", "800"))
    o.append(steps_list(386, 252, ["对每个候选 doc，构造联合输入 [query ; doc]",
                                   "交叉编码器一次性编码 → 相关性分数",
                                   "按分数降序排序，取 Top-K"], GREEN, 480))
    o.append(rect(386, 402, 460, 64, "#EEF7F1", rx=8, stroke="#CFE9DA", sw=1))
    o.append(text(402, 424, "双塔 Bi-Encoder：enc(q)·enc(d) 分开编码，快但钝", 11.5, MUTE, "600"))
    o.append(text(402, 446, "交叉 Cross-Encoder：f([q;d]) 联合编码，慢但精", 11.5, GREEN, "800"))
    o.append(arrow(866, 336, 896, 336, MUTE, 2.6))
    o.append(iocard(898, 186, 312, 300, "输出", ORANGE, ["精排后的 Top-K", "近似名被拉开区分", "如 GCP 与 GLP 不再混"]))
    _exband(o, ["score = CrossEncoder([query ; doc])；只在小候选集（几十条）上跑，成本可控。",
                "作用：把“非临床 vs 药学”“GCP vs GLP”这类细微差异分开。"])
    return svg("".join(o))


# ============================================================ ALGO: Sort / TopK
def algo_sort():
    return _algo(
        "排序裁剪（TopK / SortByFullname）：把结果排好序并裁到预算内，便于阅读、去重与溯源。",
        ["结果集（带分数或 fullname）", "K 或 token 预算"],
        ["TopK：按分数部分排序取前 K（堆，O(n·log K)）",
         "SortByFullname：按层级地址字典序排",
         "→ 还原“文档原顺序”，读着顺、好去重",
         "Budget：按 token 预算截断"],
        ["有序、够用的结果集", "按 fullname 排 = 文档顺序", "→ 交给 Ground / Answer"],
        ["例：8 条独有法规按 fullname 排序后逐条列出，附出处；超预算则截断。",
         "SortByfullname 让相邻条款/同章节内容自然聚在一起。"],
        cin=BLUE, cmid=GREEN)


# ============================================================ ALGO: 校验控制
def algo_verify():
    o = [cap("校验控制：SetCheck 保“不漏”，ProvenanceCheck 保“不编”，Threshold 保“不错答”。不达标可回环重规划。")]
    cards = [
        ("SetCheck 完整性", GREEN,
         ["结果集合 vs “应有集合”（图上确定性算出）", "求差集 → 找出漏项", "缺 → 回填 / 重试"]),
        ("ProvenanceCheck 溯源", ORANGE,
         ["对每条结果的名字", "在原文块里做字符串匹配", "匹配不上 = 幻觉 → 剔除"]),
        ("Threshold 兜底", RED,
         ["若最高检索分 < 阈值 τ", "则 abstain（不硬答）", "返回“最接近候选”"]),
    ]
    for i, (t, c, steps) in enumerate(cards):
        x = 70 + i * 388
        o.append(card(x, 186, 366, 300, accent=c))
        o.append(pill(x + 22, y_ := 206, 190, 28, c, t, 13, "#FFFFFF", "800"))
        o.append(steps_list(x + 24, 262, steps, c, 340))
    _exband(o, ["三者串联：SetCheck（不漏）→ ProvenanceCheck（不编）→ Threshold（不错答）。",
                "SetCheck 的“应有集合”来自结构化通道（如 IND 的全部 requires）；不达标可触发 Replan 有界回环。"])
    return svg("".join(o))


# ============================================================ ALGO: LLM 加工
def algo_llm():
    o = [cap("LLM 加工算子：固定代码 + 模板提示词 + 低温 → 结构化输出。是受控的“算子”，不是任意代码（安全）。")]
    o.append(iocard(70, 186, 268, 300, "输入", BLUE, ["检索/组装好的块", "任务参数（field / aspect / 模板）", "低温 temperature≈0"]))
    o.append(arrow(340, 336, 370, 336, MUTE, 2.6))
    o.append(card(372, 186, 472, 300, accent=PURPLE))
    o.append(pill(392, 202, 96, 26, PURPLE, "统一模式", 12.5, "#FFFFFF", "800"))
    o.append(text(392, 250, "固定代码路径 → 填模板 → 调 LLM → 解析结构化输出", 12.6, INK, "700"))
    rows = [("Summarize", "块 → 摘要文本"), ("Extract", "块 + field → 抽取的值"),
            ("Compare", "A,B,aspect → 结构化异同"), ("Generate", "context+模板 → 答案+引用"),
            ("Judge", "→ 打分 / 判定")]
    for i, (t, d) in enumerate(rows):
        y = 286 + i * 36
        o.append(text(392, y, t, 12.8, PURPLE, "800", ff=MONO))
        o.append(text(500, y, d, 12.6, MUTE, "600"))
    o.append(arrow(846, 336, 876, 336, MUTE, 2.6))
    o.append(iocard(878, 186, 332, 300, "输出", GREEN, ["结构化结果（JSON/文本）", "Generate 逐条 + fullname 引用", "可解析、可校验"]))
    _exband(o, ["安全：提示词是固定模板、代码路径固定——不是 LLM 生成并执行任意代码。",
                "Generate 强约束：只依据检索结果、逐条列出、不增删改名、每条标出处。"])
    return svg("".join(o))


# ============================================================ ALGO: AI Search 交互
def algo_aisearch():
    o = [cap("会与 Azure AI Search 交互的算子共 5 个（实线=请求“发”，卡内注明“收”）；其余算子走 边表/图、内存 或 LLM，不碰 AI Search。")]
    bx, by, bw, bh = 445, 200, 392, 356
    o.append(rect(bx, by, bw, bh, "#0E2E52", rx=16))
    o.append(text(bx + bw / 2, by + 32, "Azure AI Search", 18, "#FFFFFF", "800", anchor="middle"))
    o.append(rect(bx + 22, by + 50, bw - 44, 130, "#16406E", rx=12, stroke=BLUE, sw=1.4))
    o.append(text(bx + 42, by + 82, "块索引 (blocks)", 15, "#DCEBFA", "800"))
    o.append(text(bx + 42, by + 108, "向量 index · 原文 text", 12.5, "#9FC2E6", "600"))
    o.append(text(bx + 42, by + 130, "fullname · 可过滤字段", 12.5, "#9FC2E6", "600"))
    o.append(rect(bx + 22, by + 196, bw - 44, 130, "#123F52", rx=12, stroke=TEAL, sw=1.4))
    o.append(text(bx + 42, by + 228, "实体索引 (entities)", 15, "#D3EFEE", "800"))
    o.append(text(bx + 42, by + 254, "名称 · 别名 aliases", 12.5, "#9FD6D2", "600"))
    o.append(text(bx + 42, by + 276, "属性 status / type…", 12.5, "#9FD6D2", "600"))

    def opcard(x, y, name, send, recv, tag, c):
        s = card(x, y, 310, 82, accent=c)
        tw = len(tag) * 15 + 18
        s += text(x + 22, y + 30, name, 15, INK, "800")
        s += pill(x + 310 - tw - 12, y + 13, tw, 24, c, tag, 11.5, "#FFFFFF", "800")
        s += text(x + 22, y + 52, "发 " + send, 11.3, MUTE, "600")
        s += text(x + 22, y + 70, "收 " + recv, 11.3, INK, "700")
        return s

    # left ops → 块索引
    o.append(opcard(70, 216, "Seed · 向量检索", "查询向量 + filter", "Top-k 块 + 相似度", "向量/混合", RED))
    o.append(opcard(70, 322, "FilterField · 过滤", "OData filter(status/type)", "过滤后集合", "下推", BLUE))
    o.append(opcard(70, 428, "Ground · 取原文", "block id 批量 get", "块原文 + fullname", "取数", GREEN))
    o.append(arrow(382, 250, 465, 268, RED, 2.2))
    o.append(arrow(382, 356, 465, 300, BLUE, 2.2))
    o.append(arrow(382, 462, 465, 332, GREEN, 2.2))
    # right ops → 实体索引
    o.append(opcard(900, 270, "Resolve · 精确/别名", "精确名 / 别名 关键词", "实体记录", "关键词", BLUE))
    o.append(opcard(900, 392, "ScanEntities · 枚举", "filter(type = X)", "实体列表", "枚举", TEAL))
    o.append(arrow(898, 300, 818, 430, BLUE, 2.2))
    o.append(arrow(898, 422, 818, 470, TEAL, 2.2))

    o.append(rect(70, 576, 1140, 56, PANEL, rx=12, stroke=LINE, sw=1))
    o.append(rect(70, 576, 6, 56, MUTE, rx=3))
    o.append(text(92, 602, "不与 AI Search 交互：Traverse · Lift · Intersect / Diff / Union · Dedup · Rerank · SetCheck · Threshold · LLM 加工",
                  13, MUTE, "700"))
    o.append(text(92, 622, "→ 它们在 边表 / 图存储 或 内存 里跑，或调用 LLM；只有上面 5 个会打 AI Search。", 12, FAINT, "600"))
    return svg("".join(o))
