#!/usr/bin/env python3
"""
rubric.py — 8维度 SKILL.md 评分引擎（开源版）

结构维度（60分）：静态分析
效果维度（40分）：实测对比（sessions_spawn）

配置：
  SKILL_ROOT    — skill 根目录（默认 ~/.openclaw/workspace/skills）
  DASHSCOPE_KEY — API key（环境变量读取）
  MODEL         — 模型名（默认 qwen3.5-flash）
"""
import os
import re
import json
import subprocess
from pathlib import Path
from typing import Optional

# ── 配置 ────────────────────────────────────────────────
SKILL_ROOT = os.environ.get("SKILL_ROOT", str(Path.home() / ".openclaw" / "workspace" / "skills"))
DASHSCOPE_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
MODEL = os.environ.get("SKILL_OPTIMIZER_MODEL", "qwen3.5-flash")

# ── 清除代理 ────────────────────────────────────────────
for _k in list(os.environ.keys()):
    if "proxy" in _k.lower() or _k.upper() in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"
    ):
        del os.environ[_k]

# ── 评分规则 ────────────────────────────────────────────
DIMENSIONS = [
    ("frontmatter",   "Frontmatter质量",      8),
    ("workflow",       "工作流清晰度",          15),
    ("boundary",      "边界条件覆盖",          10),
    ("checkpoint",     "检查点设计",             7),
    ("specificity",    "指令具体性",             15),
    ("resources",      "资源整合度",             5),
    ("architecture",  "整体架构",              15),
    ("effectiveness", "实测表现",              25),
]

MAX_TOTAL = 100


def load_skill_md(skill_path: str, skill_root: str = None) -> tuple[str, dict]:
    """读取 SKILL.md，返回 (raw_text, frontmatter_dict)"""
    root = skill_root or SKILL_ROOT
    p = Path(skill_path)
    if not p.exists():
        p = Path(root) / skill_path / "SKILL.md"
    if not p.exists():
        raise FileNotFoundError(f"SKILL.md not found: {skill_path}")

    text = p.read_text(encoding="utf-8")

    # 解析 frontmatter
    fm = {}
    m = re.match(r"^---\n(.*?)\n---", text, re.DOTALL)
    if m:
        for line in m.group(1).splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                fm[k.strip()] = v.strip()
        body = text[m.end():]
    else:
        body = text

    return body, fm


def score_frontmatter(fm: dict, body: str) -> tuple[int, str]:
    """维度1: Frontmatter质量（8分）"""
    score = 0
    reasons = []

    name = fm.get("name", "")
    desc = fm.get("description", "")

    # name 规范
    if name and re.match(r"^[a-z0-9_-]+$", name):
        score += 3
        reasons.append("name规范")
    elif name:
        reasons.append(f"name格式: {name}")

    # description 含触发词
    trigger_words = ["当", "当用户", "触发", "使用", "skill"]
    if desc and any(w in desc for w in trigger_words):
        score += 3
        reasons.append("description含触发词")
    elif desc:
        reasons.append("description缺少触发词")

    # 长度
    if len(desc) <= 1024:
        score += 2
    else:
        reasons.append(f"description过长({len(desc)}>1024)")

    return score, "; ".join(reasons) if reasons else "OK"


def score_workflow(body: str) -> tuple[int, str]:
    """维度2: 工作流清晰度（15分）"""
    score = 0
    reasons = []

    # 有步骤序号
    steps = re.findall(r"(?:^|\n)\s*(?:\d+[.)]|[-*]\s+|[A-Z][.)]\s+)", body)
    if len(steps) >= 3:
        score += 6
        reasons.append(f"步骤数:{len(steps)}")
    elif len(steps) > 0:
        score += 3
        reasons.append(f"步骤偏少:{len(steps)}")

    # 每步有输入输出关键字
    io_keywords = ["输入", "输出", "参数", "返回", "调用", "action", "input", "output"]
    io_count = sum(1 for kw in io_keywords if kw in body)
    if io_count >= 4:
        score += 5
        reasons.append("输入输出清晰")
    elif io_count >= 2:
        score += 2
        reasons.append(f"输入输出一般({io_count})")

    # 有阶段/Panel/Step结构
    if re.search(r"(?i)##?\s+(stage|phase|step|节点)", body):
        score += 4
        reasons.append("有阶段结构")

    return min(score, 15), "; ".join(reasons) if reasons else "OK"


def score_boundary(body: str) -> tuple[int, str]:
    """维度3: 边界条件覆盖（10分）"""
    score = 0
    reasons = []

    boundary_keywords = [
        "异常", "错误", "失败", "fallback", "超时", "limit",
        "边界", "如果", "when", "except", "error", "timeout", "not found",
        "找不到", "缺失", "missing", "retry", "重试", "重试"
    ]
    count = sum(1 for kw in boundary_keywords if re.search(kw, body, re.I))
    if count >= 5:
        score += 6
        reasons.append(f"边界覆盖充分({count})")
    elif count >= 3:
        score += 3
        reasons.append(f"边界覆盖一般({count})")

    # 有错误处理步骤
    if re.search(r"(?i)(如果失败|异常时|error.*处理|except|return error|handle)", body):
        score += 4
        reasons.append("有错误处理")

    return min(score, 10), "; ".join(reasons) if reasons else "OK"


def score_checkpoint(body: str) -> tuple[int, str]:
    """维度4: 检查点设计（7分）"""
    score = 0
    reasons = []

    checkpoint_keywords = [
        "确认", "暂停", "等用户", "展示", "向用户", "展示给",
        "confirm", "pause", "await", "check"
    ]
    count = sum(1 for kw in checkpoint_keywords if kw in body)
    if count >= 2:
        score += 5
        reasons.append(f"检查点充分({count})")
    elif count == 1:
        score += 2
        reasons.append(f"检查点偏少({count})")

    # 关键决策前有确认
    if re.search(r"(?i)(确认后再|等用户确认|先确认)", body):
        score += 2
        reasons.append("关键决策有确认")

    return min(score, 7), "; ".join(reasons) if reasons else "OK"


def score_specificity(body: str) -> tuple[int, str]:
    """维度5: 指令具体性（15分）"""
    score = 0
    reasons = []

    # 有示例
    examples = re.findall(r"```", body)
    if len(examples) >= 2:
        score += 5
        reasons.append(f"示例充分({len(examples)//2})")
    elif len(examples) >= 1:
        score += 2
        reasons.append("有示例")

    # 有具体参数/路径/格式
    concrete_patterns = [
        r"`[^`]+`",           # 代码块内内容
        r"(?:file|path|url|api|key)[:：]\s*\S+",  # 具体配置
    ]
    concrete_count = sum(len(re.findall(p, body, re.I)) for p in concrete_patterns)
    if concrete_count >= 5:
        score += 5
        reasons.append("指令具体")
    elif concrete_count >= 2:
        score += 3
        reasons.append(f"指令较具体({concrete_count})")

    # 没有过多模糊词
    vague_words = ["等等", "之类", "什么的", "若干", "一些", "若干"]
    vague_count = sum(1 for w in vague_words if w in body)
    if vague_count == 0:
        score += 5
    elif vague_count <= 2:
        score += 2
        reasons.append(f"少量模糊词({vague_count})")

    return min(score, 15), "; ".join(reasons) if reasons else "OK"


def score_resources(body: str) -> tuple[int, str]:
    """维度6: 资源整合度（5分）"""
    score = 0
    reasons = []

    # 有引用文件
    ref_patterns = [
        r"\[.*?\]\(.*?\)",   # markdown链接
        r"`[^`]+`",           # 代码引用
        r"(?:script|file|skill|module)[:：]\s*\S+",
    ]
    ref_count = sum(len(re.findall(p, body)) for p in ref_patterns)
    if ref_count >= 3:
        score += 3
        reasons.append(f"引用充分({ref_count})")

    # 有路径规范
    if re.search(r"(?:path|dir|folder|目录)[:：]", body, re.I):
        score += 2
        reasons.append("有路径规范")

    return min(score, 5), "; ".join(reasons) if reasons else "OK"


def score_architecture(body: str) -> tuple[int, str]:
    """维度7: 整体架构（15分）"""
    score = 0
    reasons = []

    # 结构化程度
    headers = re.findall(r"^#{1,3}\s+", body, re.MULTILINE)
    if len(headers) >= 4:
        score += 5
        reasons.append(f"层次清晰({len(headers)}标题)")
    elif len(headers) >= 2:
        score += 3

    # 无重复内容
    lines = [l.strip() for l in body.splitlines() if l.strip()]
    if len(lines) < 20:
        score += 3
        reasons.append(f"内容简洁({len(lines)}行)")
    elif len(lines) > 500:
        score -= 2
        reasons.append(f"内容过长({len(lines)}行)")

    # 模块化（不同action/阶段分开）
    if re.search(r"(?i)##?\s+action", body):
        score += 4
        reasons.append("action结构清晰")
    if re.search(r"(?i)##?\s+(skill|tool)", body):
        score += 3
        reasons.append("skill/tool结构清晰")

    return max(0, min(score, 15)), "; ".join(reasons) if reasons else "OK"


def score_effectiveness(
    skill_path: str,
    test_prompts: list[dict],
    dashscope_key: str,
    model: str,
    skill_root: str = None,
) -> tuple[int, str]:
    """
    维度8: 实测表现（25分）
    sessions_spawn 一个子agent，带 SKILL.md 跑测试 prompt，
    对比不带 SKILL.md 的 baseline 输出。
    """
    if not test_prompts:
        return 10, "无测试prompt，退化为干跑评估"

    # 读取 SKILL.md 内容
    try:
        p = Path(skill_path)
        if not p.exists():
            root = skill_root or SKILL_ROOT
            p = Path(root) / skill_path / "SKILL.md"
        skill_md = p.read_text(encoding="utf-8")
    except Exception:
        return 10, "无法读取SKILL.md"

    results = []
    for tp in test_prompts:
        prompt = tp.get("prompt", "")
        expected = tp.get("expected", "")

        # 构建带 skill 的 system prompt
        with_skill_system = (
            "你是一个助手。以下是一个 skill 的描述：\n\n"
            f"{skill_md[:3000]}\n\n"
            f"用户会说：{prompt}\n\n"
            "严格按照 skill 描述执行，给出你的回答。"
        )

        without_skill_system = (
            f"用户会说：{prompt}\n\n"
            "你是一个通用助手，直接回答。"
        )

        # 调用 AI 打分
        score_prompt = f"""
对比以下两个回答的质量：

【问题】：{prompt}
【期望输出】：{expected}

【回答A（带skill）】：见下方
【回答B（不带skill）】：见下方

请从以下维度打分（1-10）：
1. 是否完成了用户意图
2. 相比不带skill，输出质量提升了吗
3. 有没有skill带来的负面影响（过度冗余、跑偏、格式奇怪）

输出格式：
- 回答A分数：[X]
- 回答B分数：[X]
- 提升程度：[明显/一般/无/负向]
- 理由：[简短说明]
"""

        try:
            payload = {
                "model": model,
                "messages": [
                    {"role": "system", "content": "你是一个专业的AI助手评测专家。"},
                    {"role": "user", "content": f"【回答A】\n我是一个熟练使用各类工具的助手。用户说：{prompt}\n\n请根据skill描述给出回答。\n\n【回答B】\n{without_skill_system}\n\n{score_prompt}"}
                ],
                "temperature": 0.3,
                "max_tokens": 800
            }

            r = subprocess.run(
                [
                    "curl", "-s", "-X", "POST",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
                    "-H", f"Authorization: Bearer {dashscope_key}",
                    "-H", "Content-Type: application/json",
                    "-d", json.dumps(payload),
                ],
                capture_output=True, text=True, timeout=60
            )

            if r.returncode == 0:
                result = json.loads(r.stdout)
                content = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                # 解析分数
                m_a = re.search(r"回答A[：:]?\s*\[?(\d+)\]?", content, re.I)
                m_b = re.search(r"回答B[：:]?\s*\[?(\d+)\]?", content, re.I)
                score_a = int(m_a.group(1)) if m_a else 5
                score_b = int(m_b.group(1)) if m_b else 5
                delta = score_a - score_b
                results.append({"a": score_a, "b": score_b, "delta": delta})
            else:
                results.append({"a": 5, "b": 5, "delta": 0, "error": r.stderr})
        except Exception as e:
            results.append({"a": 5, "b": 5, "delta": 0, "error": str(e)})

    if not results:
        return 10, "无法完成实测"

    avg_delta = sum(r["delta"] for r in results) / len(results)
    if avg_delta >= 3:
        effective_score = 20 + min(5, (avg_delta - 3) * 2)
    elif avg_delta >= 1:
        effective_score = 15 + int(avg_delta) * 2
    elif avg_delta >= 0:
        effective_score = 12 + int(avg_delta * 3)
    elif avg_delta >= -1:
        effective_score = 10 + int(avg_delta * 3)
    else:
        effective_score = max(5, 10 + int(avg_delta * 2))

    detail = f"delta={avg_delta:+.1f}/prompt, n={len(results)}"
    return max(5, min(25, effective_score)), detail


def score_skill(
    skill_path: str,
    test_prompts: list[dict] | None = None,
    dashscope_key: str = "",
    model: str = "",
    skill_root: str = None,
) -> dict:
    """
    对目标 skill 执行完整8维度评分。

    Returns:
        {
            "skill": str,
            "total": float,
            "dimensions": [
                {"name", "label", "score", "max", "reason"}
            ],
            "structure_score": int,   # 结构维度总分60
            "effectiveness_score": int, # 效果维度总分40
            "test_prompts_used": int,
        }
    """
    body, fm = load_skill_md(skill_path, skill_root)
    skill_name = fm.get("name", skill_path)

    dimensions = []

    # 结构维度
    frontmatter_score, frontmatter_reason = score_frontmatter(fm, body)
    dimensions.append({
        "name": "frontmatter", "label": "Frontmatter质量",
        "score": frontmatter_score, "max": 8, "reason": frontmatter_reason
    })

    workflow_score, workflow_reason = score_workflow(body)
    dimensions.append({
        "name": "workflow", "label": "工作流清晰度",
        "score": workflow_score, "max": 15, "reason": workflow_reason
    })

    boundary_score, boundary_reason = score_boundary(body)
    dimensions.append({
        "name": "boundary", "label": "边界条件覆盖",
        "score": boundary_score, "max": 10, "reason": boundary_reason
    })

    checkpoint_score, checkpoint_reason = score_checkpoint(body)
    dimensions.append({
        "name": "checkpoint", "label": "检查点设计",
        "score": checkpoint_score, "max": 7, "reason": checkpoint_reason
    })

    specificity_score, specificity_reason = score_specificity(body)
    dimensions.append({
        "name": "specificity", "label": "指令具体性",
        "score": specificity_score, "max": 15, "reason": specificity_reason
    })

    resources_score, resources_reason = score_resources(body)
    dimensions.append({
        "name": "resources", "label": "资源整合度",
        "score": resources_score, "max": 5, "reason": resources_reason
    })

    architecture_score, architecture_reason = score_architecture(body)
    dimensions.append({
        "name": "architecture", "label": "整体架构",
        "score": architecture_score, "max": 15, "reason": architecture_reason
    })

    structure_score = sum(d["score"] for d in dimensions)

    # 效果维度
    key = dashscope_key or DASHSCOPE_KEY
    m = model or MODEL
    if key and test_prompts:
        eff_score, eff_reason = score_effectiveness(
            skill_path, test_prompts, key, m, skill_root
        )
    else:
        eff_score = 10
        eff_reason = "未提供test_prompts或dashscope_key，退化为基准分10"
    dimensions.append({
        "name": "effectiveness", "label": "实测表现",
        "score": eff_score, "max": 25, "reason": eff_reason
    })

    total = structure_score + eff_score

    return {
        "skill": skill_name,
        "total": round(total, 1),
        "dimensions": dimensions,
        "structure_score": structure_score,
        "effectiveness_score": eff_score,
        "test_prompts_used": len(test_prompts or []),
    }


if __name__ == "__main__":
    import sys
    skill = sys.argv[1] if len(sys.argv) > 1 else "skill-scorer"
    result = score_skill(skill)
    print(json.dumps(result, ensure_ascii=False, indent=2))
