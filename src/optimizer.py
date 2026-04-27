#!/usr/bin/env python3
"""
optimizer.py — skill 优化循环 + 棘轮机制（开源版）

存储结构：
  ~/.openclaw/skill-optimizer/
  ├── snapshots/{skill_name}/{ts}/SKILL.md  ← 每次优化前的快照
  ├── results/{skill_name}.json             ← 评测历史
  └── logs/round-{n}.md                     ← 每轮优化日志

配置：
  SKILL_ROOT    — skill 根目录
  DASHSCOPE_KEY — API key
  MODEL         — 模型名
"""
import os
import re
import json
import time
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
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

BASE_DIR = Path.home() / ".openclaw" / "skill-optimizer"
SNAPSHOT_DIR = BASE_DIR / "snapshots"
RESULTS_DIR = BASE_DIR / "results"
LOGS_DIR = BASE_DIR / "logs"

for _d in [SNAPSHOT_DIR, RESULTS_DIR, LOGS_DIR]:
    _d.mkdir(parents=True, exist_ok=True)


# ── 辅助 ────────────────────────────────────────────────

def find_skill_md(skill_path: str) -> Path:
    """定位 SKILL.md"""
    candidates = [
        Path(skill_path) / "SKILL.md",
        Path(skill_path),
        Path(SKILL_ROOT) / skill_path / "SKILL.md",
        Path(SKILL_ROOT) / skill_path,
    ]
    for p in candidates:
        if p.exists() and p.stat().st_size > 0:
            return p
    raise FileNotFoundError(f"SKILL.md not found: {skill_path}")


def find_skill_dir(skill_path: str) -> Path:
    """定位 skill 目录"""
    candidates = [
        Path(skill_path),
        Path(SKILL_ROOT) / skill_path,
    ]
    for p in candidates:
        if p.exists():
            return p
    raise FileNotFoundError(f"Skill dir not found: {skill_path}")


def snapshot(skill_name: str) -> Path:
    """对 skill 当前版本打快照，返回快照目录"""
    skill_dir = find_skill_dir(skill_name)
    skill_md_path = find_skill_md(skill_name)

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    snap_dir = SNAPSHOT_DIR / skill_name / ts
    snap_dir.mkdir(parents=True, exist_ok=True)

    dest = snap_dir / "SKILL.md"
    shutil.copy2(skill_md_path, dest)

    for fname in ["skill.py", "skill.js", "index.js"]:
        src = skill_dir / fname
        if src.exists():
            shutil.copy2(src, snap_dir / fname)

    return snap_dir


def load_results(skill_name: str) -> dict:
    """加载评测历史"""
    f = RESULTS_DIR / f"{skill_name}.json"
    if f.exists():
        return json.loads(f.read_text())
    return {
        "skill": skill_name,
        "baseline": None,
        "rounds": [],
        "current_score": 0,
        "current_dimensions": {},
    }


def save_results(skill_name: str, data: dict):
    """保存评测历史"""
    f = RESULTS_DIR / f"{skill_name}.json"
    f.write_text(json.dumps(data, ensure_ascii=False, indent=2))


def load_skill_md_content(skill_name: str) -> str:
    """读取当前 SKILL.md 内容"""
    return find_skill_md(skill_name).read_text(encoding="utf-8")


def write_skill_md(skill_name: str, content: str):
    """写入 SKILL.md"""
    p = find_skill_md(skill_name)
    p.write_text(content, encoding="utf-8")


def call_ai(prompt: str, system: str = "", max_tokens: int = 1500) -> str:
    """调用 LLM"""
    dashscope_key = DASHSCOPE_KEY
    if not dashscope_key:
        return ""
    
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    payload = {
        "model": MODEL,
        "messages": msgs,
        "temperature": 0.5,
        "max_tokens": max_tokens
    }

    r = subprocess.run(
        [
            "curl", "-s", "-X", "POST",
            "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
            "-H", f"Authorization: Bearer {dashscope_key}",
            "-H", "Content-Type: application/json",
            "-d", json.dumps(payload),
        ],
        capture_output=True, text=True, timeout=90
    )
    if r.returncode != 0:
        return ""
    try:
        return json.loads(r.stdout)["choices"][0]["message"]["content"]
    except:
        return ""


# 不可文字优化的维度（得分来自实测，文字改动无效）
NON_IMPROVABLE = {"effectiveness", "实测表现"}

# ── 改进策略（重写）───────────────────────────────────────
#
# 核心原则：AI 输出的必须是可以直接替换/插入到 SKILL.md 的具体内容块
# 不是"建议"，是"可以直接贴进去的 markdown"

IMPROVEMENT_PROMPTS = {
    "frontmatter": """你是一个 SKILL.md frontmatter 专家。请根据以下原则生成改进后的 frontmatter。

【重要】你只能输出一段纯文本，必须以 --- 开头，以 --- 结束。不要加任何解释、前言、后记。直接输出可以贴进文件的 frontmatter。

原则：
- name: 必须是规范的 kebab-case（小写+连字符），如 "skill-scorer"
- description: 必须包含三部分：(1)做什么 (2)何时用 (3)触发词（如 "当用户说...时使用"）
- 长度: description ≤ 1024 字符

当前 SKILL.md 的 name 是 "{name}"（如果不符合规范也要改正）。

输出格式（严格按照）：
---
name: xxx
description: xxx
---
""",

    "boundary": """你是一个 SKILL.md 错误处理设计专家。请为这个 skill 的 SKILL.md 补充边界条件章节。

评分标准（10分）：
- 包含 ≥4 个异常/边界关键词（timeout/error/limit/如果/失败/fallback）
- 有明确的"如果X失败，则Y"错误处理
- 有超时/限制说明

请生成一个 ## 边界条件 章节，包含：
1. 常见错误场景及处理方式（至少3个，如文件不存在/超时/API报错/参数缺失）
2. 每个场景：条件 → 处理方式
3. 超时和限制说明

格式要求：
- 用 ### 错误场景 作为小标题
- 每个场景格式：### 场景名\n**条件**：\n**处理**：
- 总字数 150-400 字

请直接输出完整的 ## 边界条件 章节内容，可以直接插入 SKILL.md。""",

    "checkpoint": """你是一个 SKILL.md 安全设计专家。请为这个 skill 的 SKILL.md 补充检查点章节。

评分标准（7分）：
- ≥2 个用户确认点
- 关键决策前有确认提示

请生成一个 ## 检查点 章节，说明：
1. 在哪些操作前需要用户确认（至少2个，如删除/覆盖/外部发送）
2. 确认的格式和措辞

格式要求：
- 用编号列表，每个确认点一行
- 确认措辞要具体，如："操作前展示给用户：[具体内容]，等用户回复 确认/取消 再继续"
- 总字数 80-200 字

请直接输出完整的 ## 检查点 章节内容，可以直接插入 SKILL.md。""",

    "workflow": """你是一个 SKILL.md 工作流设计专家。请改进这个 skill 的工作流章节。

评分标准（15分）：
- 有序号步骤（≥3步）
- 每步有明确的输入/输出说明
- 有 action 路由表

当前工作流内容可能很少或不完整。

请生成一个完整的 ## 工作流 章节，包含：
1. 概述（一句话说明整体流程）
2. 步骤列表（用 1. 2. 3. 格式），每步：
   - 步骤名称
   - 输入：xxx
   - 输出：xxx
3. action 路由表（如有多个 action）

总字数 200-400 字。

请直接输出完整的 ## 工作流 章节内容，可以直接插入 SKILL.md。""",

    "specificity": """你是一个 SKILL.md 写作专家。请增强这个 skill 的指令具体性。

评分标准（15分）：
- 有代码示例（≥2个 ``` 块）
- 有具体参数/路径/格式说明
- 无模糊词（无"等等"/"之类"/"若干"）

请检查现有内容，补充：
1. 更具体的 action 参数说明（如 action=xxx，参数 yyy 类型/必填/默认值）
2. 一个额外的代码示例（如果现有不够2个）
3. 路径规范说明（如文件存放位置）

请直接输出改进后的相关章节内容，不要输出整篇文档。""",

    "architecture": """你是一个 SKILL.md 架构设计专家。请改进这个 skill 的整体结构。

评分标准（15分）：
- ≥4 个 ## 标题
- 结构层次清晰（## > ###）
- 无重复内容
- 20-500 行

当前可能结构太少或层次不清。

请输出一个改进后的目录结构建议，以及需要补充/修改的核心章节（每个章节输出完整内容）。
如果某个关键章节缺失（如无 ## 概述 / ## 约束 等），请生成该章节。
总字数 300-600 字。

请直接输出完整的章节内容，可以直接插入 SKILL.md。""",

    "resources": """你是一个 SKILL.md 资源整合专家。请为这个 skill 的 SKILL.md 补充资源/依赖章节。

评分标准（5分）：
- 引用路径正确（文件路径存在）
- 依赖外部服务/工具/API 有明确声明
- 引用充分（至少 3 处）

请生成一个 ## 资源 / ## 依赖 / ## 相关文件 章节，包含：
1. 核心依赖文件（如 skill.py、services/、配置等）
2. 外部依赖（如 API key、端口号、服务地址）
3. 参考文档/链接（如有）

格式要求：
- 用表格或列表，每项注明路径和作用
- 外部依赖需注明如何获取/配置
- 总字数 80-200 字

请直接输出完整的 ## 资源 章节内容，可以直接插入 SKILL.md。""",

    "effectiveness": """实测表现维度（25分）无法通过文字改进来提升，因为它需要实际运行测试。

建议：
1. 提供 test_prompts 参数给 optimizer，我会用 sessions_spawn 跑实测对比
2. 当前阶段先优化其他维度（结构分），实测留到有 test_prompts 时再做

请输出一句话说明这个维度需要实测验证，不要修改 SKILL.md。""",
}


def improve_dimension(
    body: str,
    dimension_name: str,
    dimension_label: str,
    current_score: int,
    max_score: int,
    critique_issues: list = None,
) -> tuple[str, str]:
    """
    针对最低分维度生成改进方案并执行编辑。
    融合 critique 的 P0/P1 问题。
    返回 (new_body, change_summary)
    """
    # 1. 解析 frontmatter 和 body
    fm_match = re.match(r"^---\n(.*?)\n---\n", body, re.DOTALL)
    if fm_match:
        fm_block = fm_match.group(0)
        fm_text = fm_match.group(1)
        body_without_fm = body[fm_match.end():]
    else:
        fm_block = ""
        fm_text = ""
        body_without_fm = body

    # 提取 name（用于 frontmatter 改进）
    name_match = re.search(r"^name:\s*(.+)$", fm_text, re.MULTILINE)
    current_name = name_match.group(1).strip() if name_match else "unknown-skill"

    # 2. 生成新内容（融合 critique 问题）
    prompt_template = IMPROVEMENT_PROMPTS.get(dimension_name, "")
    if not prompt_template:
        return body, "no prompt defined"

    # 在 prompt 中融入 critique 问题
    critique_hint = ""
    if critique_issues:
        relevant = [i for i in critique_issues if dimension_name.lower() in i.get("file", "").lower() or dimension_name.lower() in i.get("issue", "").lower()]
        if relevant:
            critique_hint = "\n\n【额外要求】请同时修复以下问题：\n" + "\n".join(f"- {i['issue']}" for i in relevant[:3])
    
    prompt = prompt_template.format(name=current_name) + critique_hint
    system = f"你是 SKILL.md 优化专家。当前「{dimension_label}」维度得分 {current_score}/{max_score}，需要针对性改进。"

    result = call_ai(prompt, system=system, max_tokens=1500)
    if not result or len(result.strip()) < 20:
        return body, "AI 返回内容过短，未执行修改"

    # 3. 根据维度应用替换
    if dimension_name == "frontmatter":
        fm_match = re.search(r"(---.*?---\n)", result, re.DOTALL)
        if fm_match:
            new_body = fm_match.group(1) + body_without_fm
            return new_body, "frontmatter 已更新"
        return body, "frontmatter 替换失败（AI输出不含---块）"

    elif dimension_name == "boundary":
        if re.search(r"## 边界条件", body, re.I):
            new_body = re.sub(
                r"## 边界条件.*?(?=\n## |$)",
                result.strip(),
                body,
                count=1,
                flags=re.DOTALL
            )
        else:
            if re.search(r"## 工作流", body, re.I):
                new_body = re.sub(
                    r"((?:## .*?\n.*?\n*)*)(## 工作流.*?)(?=\n## |\Z)",
                    r"\1\2\n\n" + result.strip(),
                    body,
                    count=1,
                    flags=re.DOTALL
                )
            else:
                new_body = body.strip() + "\n\n" + result.strip()
        return new_body, "boundary 章节已添加/更新"

    elif dimension_name == "checkpoint":
        if re.search(r"## 检查点", body, re.I):
            new_body = re.sub(
                r"## 检查点.*?(?=\n## |$)",
                result.strip(),
                body,
                count=1,
                flags=re.DOTALL
            )
        else:
            new_body = body.strip() + "\n\n" + result.strip()
        return new_body, "checkpoint 章节已添加/更新"

    elif dimension_name == "workflow":
        if re.search(r"## 工作流", body, re.I):
            new_body = re.sub(
                r"## 工作流.*?(?=\n## |\Z)",
                result.strip(),
                body,
                count=1,
                flags=re.DOTALL
            )
        else:
            new_body = body.strip() + "\n\n" + result.strip()
        return new_body, "workflow 章节已添加/更新"

    elif dimension_name == "architecture":
        sections = re.findall(r"^## .+$", body, re.MULTILINE)
        has_overview = any("概览" in s or "概述" in s for s in sections)

        if not has_overview:
            overview_section = "\n## 概述\n\n简要说明本 skill 的核心功能和适用场景。\n"
            new_body = overview_section + body
        else:
            new_body = body

        new_body = new_body.strip() + "\n\n" + result.strip()
        return new_body, "architecture 章节已增强"

    else:
        new_body = body.strip() + "\n\n" + result.strip()
        return new_body, f"{dimension_name} 内容已追加"


# ── 主流程 ──────────────────────────────────────────────

def run_optimization(
    skill_name: str,
    test_prompts: list | None = None,
    max_rounds: int = 3,
    auto_confirm: bool = False,
    dashscope_key: str = "",
    model: str = "",
    skill_root: str = None,
    rubric_result: dict = None,
) -> dict:
    """
    执行完整优化循环（融合 critique）。
    """
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from rubric import score_skill

    key = dashscope_key or DASHSCOPE_KEY
    m = model or MODEL
    root = skill_root or SKILL_ROOT

    results = load_results(skill_name)

    # Phase 1: 基线评分
    print(f"[optimizer] 基线评分: {skill_name}")
    baseline = score_skill(
        skill_name,
        test_prompts=test_prompts,
        dashscope_key=key,
        model=m,
        skill_root=root,
    )
    baseline["at"] = datetime.now().isoformat()
    results["baseline"] = baseline
    results["current_score"] = baseline["total"]
    results["current_dimensions"] = {
        d["name"]: d["score"] for d in baseline["dimensions"]
    }
    save_results(skill_name, results)

    print(f"[optimizer] 基线评分: {baseline['total']}/100")
    for d in baseline["dimensions"]:
        print(f"  {d['label']}: {d['score']}/{d['max']} — {d['reason']}")

    # Phase 2: 优化循环
    kept = 0
    reverted = 0
    skipped_count: dict[str, int] = {}

    # 提取 critique 问题（如果提供了 rubric_result）
    critique_issues = []
    if rubric_result:
        # 从 rubric 的低分维度推断问题
        for d in rubric_result.get("dimensions", []):
            ratio = d["score"] / d["max"] if d["max"] > 0 else 1
            if ratio < 0.5:
                critique_issues.append({
                    "file": d["name"],
                    "issue": f"{d['label']}得分过低({d['score']}/{d['max']}): {d['reason']}"
                })

    for round_num in range(1, max_rounds + 1):
        print(f"\n[optimizer] === Round {round_num} ===")

        # 2.1 找最低分维度
        dims = {d["name"]: d for d in baseline["dimensions"]}
        candidates = [
            (k, v) for k, v in dims.items()
            if k not in NON_IMPROVABLE and skipped_count.get(k, 0) < 2
        ]
        if not candidates:
            print(f"[optimizer] 所有维度都卡死，停止优化")
            break
        lowest = min(candidates, key=lambda x: x[1]["score"] / x[1]["max"] if x[1]["max"] > 0 else 999)
        dim_name, dim_info = lowest
        ratio = dim_info["score"] / dim_info["max"] if dim_info["max"] > 0 else 0

        if ratio >= 0.8:
            print(f"[optimizer] 所有维度都已达到80%，无需继续优化")
            break

        print(f"[optimizer] 最低分维度: {dim_info['label']} ({dim_info['score']}/{dim_info['max']})")

        # 2.2 快照当前版本
        snap_dir = snapshot(skill_name)
        print(f"[optimizer] 快照已保存: {snap_dir}")

        # 2.3 生成改进（融合 critique 问题）
        print(f"[optimizer] 生成改进方案...")
        current_body = load_skill_md_content(skill_name)
        improved_body, change_summary = improve_dimension(
            current_body,
            dim_name,
            dim_info["label"],
            dim_info["score"],
            dim_info["max"],
            critique_issues=critique_issues,
        )
        print(f"[optimizer] 改动：{change_summary}")

        # 2.4 执行修改
        write_skill_md(skill_name, improved_body)
        print(f"[optimizer] SKILL.md 已更新")

        # 2.5 重新评分
        new_result = score_skill(
            skill_name,
            test_prompts=test_prompts,
            dashscope_key=key,
            model=m,
            skill_root=root,
        )
        new_total = new_result["total"]
        old_total = results["current_score"]

        print(f"[optimizer] 评分变化: {old_total} → {new_total}")

        # 2.6 棘轮决策
        round_record = {
            "round": round_num,
            "at": datetime.now().isoformat(),
            "target_dimension": dim_name,
            "target_label": dim_info["label"],
            "old_score": old_total,
            "new_score": new_total,
            "change_summary": change_summary,
            "snapshot": str(snap_dir),
            "improvement": "keep" if new_total > old_total else "revert",
        }

        if new_total > old_total:
            print(f"[optimizer] ✅ 涨分，保留改进")
            results["current_score"] = new_total
            results["current_dimensions"] = {
                d["name"]: d["score"] for d in new_result["dimensions"]
            }
            baseline = new_result
            kept += 1
            skipped_count.pop(dim_name, None)
        else:
            print(f"[optimizer] ❌ 降分或持平，回滚快照")
            snap_md = snap_dir / "SKILL.md"
            if snap_md.exists():
                write_skill_md(skill_name, snap_md.read_text(encoding="utf-8"))
            round_record["improvement"] = "revert"
            reverted += 1
            skipped_count[dim_name] = skipped_count.get(dim_name, 0) + 1
            if skipped_count[dim_name] >= 2:
                print(f"[optimizer] ⛔ {dim_info['label']} 连续回滚2次，自动跳过")

        results["rounds"].append(round_record)
        save_results(skill_name, results)

        # 2.7 日志
        log_file = LOGS_DIR / f"round-{datetime.now().strftime('%Y%m%d-%H%M%S')}.md"
        log_file.write_text(
            f"# Round {round_num} | {skill_name}\n\n"
            f"**最低分维度**: {dim_info['label']} ({dim_info['score']}/{dim_info['max']})\n"
            f"**改动**: {change_summary}\n"
            f"**分数变化**: {old_total} → {new_total}\n"
            f"**结果**: {'保留' if new_total > old_total else '回滚'}\n"
            f"**快照**: {snap_dir}\n",
            encoding="utf-8"
        )

        if not auto_confirm:
            print(f"[optimizer] Round {round_num} 完成，等待用户确认...")
            break

    results["kept_rounds"] = kept
    results["reverted_rounds"] = reverted
    results["final_score"] = results["current_score"]
    save_results(skill_name, results)

    return results


def get_status(skill_name: Optional[str] = None) -> dict:
    """查看评测/优化状态"""
    if skill_name:
        results = load_results(skill_name)
        return {
            "skill": skill_name,
            "has_baseline": results.get("baseline") is not None,
            "current_score": results.get("current_score", 0),
            "rounds_count": len(results.get("rounds", [])),
            "kept": results.get("kept_rounds", 0),
            "reverted": results.get("reverted_rounds", 0),
        }

    all_skills = []
    for f in RESULTS_DIR.glob("*.json"):
        sname = f.stem
        data = json.loads(f.read_text())
        all_skills.append({
            "skill": sname,
            "current_score": data.get("current_score", 0),
            "rounds": len(data.get("rounds", [])),
            "kept": data.get("kept_rounds", 0),
        })
    return {"skills": all_skills, "total": len(all_skills)}


if __name__ == "__main__":
    import sys
    args = sys.argv[1:]

    if not args:
        print("Usage:")
        print("  optimizer.py score <skill_name>")
        print("  optimizer.py optimize <skill_name> [--rounds N] [--auto]")
        print("  optimizer.py status [<skill_name>]")
        sys.exit(1)

    cmd = args[0]

    if cmd == "score":
        skill_name = args[1] if len(args) > 1 else "skill-scorer"
        import rubric
        key = os.environ.get("DASHSCOPE_API_KEY", "")
        result = rubric.score_skill(skill_name, dashscope_key=key)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "optimize":
        skill_name = args[1] if len(args) > 1 else "skill-scorer"
        max_rounds = 3
        auto = "--auto" in args
        result = run_optimization(skill_name, max_rounds=max_rounds, auto_confirm=auto)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == "status":
        skill_name = args[1] if len(args) > 1 else None
        print(json.dumps(get_status(skill_name), ensure_ascii=False, indent=2))

    else:
        print(f"Unknown command: {cmd}")
