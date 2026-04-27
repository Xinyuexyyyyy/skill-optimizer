#!/usr/bin/env python3
"""
critique.py — 锐评逻辑（开源版）

从原 critique/skill.py 整合，支持：
  - 扫描 skill 目录
  - 生成 critique.md（P0/P1/P2 问题清单）
  - 生成 manual.md（使用手册）
  - 融合 rubric 评分结果，重点分析低分维度

配置：
  SKILL_ROOT — skill 根目录
"""
import re
import json
import os
from datetime import datetime
from pathlib import Path

SKILL_ROOT = Path(os.environ.get("SKILL_ROOT", str(Path.home() / ".openclaw" / "workspace" / "skills")))


def _scan_skill(skill_name: str) -> dict:
    """扫描 skill 目录，返回文件列表和关键内容"""
    skill_dir = SKILL_ROOT / skill_name
    if not skill_dir.exists():
        return {"exists": False}

    files = {}
    for f in skill_dir.rglob("*"):
        if f.is_file() and not f.name.startswith("."):
            try:
                rel = f.relative_to(skill_dir)
                files[str(rel)] = f.read_text(encoding="utf-8")[:3000]
            except Exception:
                pass

    return {"exists": True, "skill_dir": str(skill_dir), "files": files}


def _build_critique_prompt(skill_name: str, scan: dict, rubric_result: dict = None) -> str:
    """构建锐评 prompt（融合 rubric 评分）"""
    file_list = "\n".join(f"- {k}" for k in scan["files"].keys())
    skill_md = scan["files"].get("SKILL.md", "（不存在）")[:2000]
    skill_py = scan["files"].get("skill.py", "（不存在）")[:2000]

    # 融合 rubric 评分信息
    rubric_info = ""
    if rubric_result:
        rubric_info = "\n\n## 8维评分结果（重点关注低分维度）\n\n"
        for d in rubric_result.get("dimensions", []):
            ratio = d["score"] / d["max"] if d["max"] > 0 else 1
            marker = "🔴" if ratio < 0.5 else "🟡" if ratio < 0.8 else "🟢"
            rubric_info += f"{marker} {d['label']}: {d['score']}/{d['max']} — {d['reason']}\n"

    return f"""你是锐评 Agent，独立评价 skill，不美化、不客气。

## 待评价 skill：{skill_name}

### 文件结构
{file_list}

### SKILL.md（前2000字符）
---
{skill_md}
---

### skill.py（前2000字符）
---
{skill_py}
---
{rubric_info}

## 锐评维度

1. 元数据：SKILL.md 存在、name 是 kebab-case、description 含 capabilities+triggers+context+boundaries
2. 文件结构：skill.py 存在、必要文件完整、无废弃文件
3. 代码质量：import 正确、有错误处理、有 graceful fallback
4. 自我感知：skill 能否报告自己状态、依赖的外部服务是否在运行、静默失败检测
5. 边界完整性：未处理 action 有无友好提示、参数校验

## 输出：写两个文件

### 文件1：skills/{skill_name}/critique.md
格式：
```markdown
# 锐评报告：{skill_name}
评分：/100

## 检查结果
| 维度 | 状态 | 问题 |
...

## P0 问题（必须修复）
1. [问题] 文件：... 当前：... 修复：...

## P1 问题（建议修复）
1. ...
```

### 文件2：skills/{skill_name}/manual.md
格式（给非工程师看的说明书）：
```markdown
# {skill_name} 使用手册

## 一句话定位
## 在系统中的位置
## 你能做什么操作（表格）
## 它依赖什么
## 已知问题
## 状态检查
```

## JSON 格式输出（供写入 critique.md 的原始数据）

```json
{{
  "metadata_ok": true/false,
  "metadata_issues": [],
  "structure_ok": true/false,
  "structure_issues": [],
  "code_ok": true/false,
  "code_issues": [],
  "self_aware": true/false,
  "self_aware_issues": [],
  "boundary_ok": true/false,
  "boundary_issues": [],
  "overall_score": 0-100,
  "p0_fixes": [{{"file":"","issue":"","current":"","fix":""}}],
  "p1_fixes": [{{"file":"","issue":"","fix":""}}]
}}
```

注意：fix 字段给具体可执行的命令或代码片段，不是描述文字。
"""


def _write_critique_report(skill_name: str, report: dict) -> str:
    """将锐评报告写入 critique.md"""
    skill_dir = SKILL_ROOT / skill_name
    report_file = skill_dir / "critique.md"

    p0_text = ""
    for i, fix in enumerate(report.get("p0_fixes", []), 1):
        p0_text += f"""
### P0-{i}：{fix['issue']}
文件：{fix['file']}
当前代码：{fix.get('current', 'N/A')}
修复：{fix['fix']}
"""

    p1_text = ""
    for i, fix in enumerate(report.get("p1_fixes", []), 1):
        p1_text += f"""
### P1-{i}：{fix['issue']}
文件：{fix['file']}
修复：{fix['fix']}
"""

    content = f"""# 锐评报告：{skill_name}

**生成时间**：{datetime.now().strftime('%Y-%m-%d %H:%M')}
**综合评分**：{report.get('overall_score', 'N/A')}/100

## 检查结果

| 维度 | 状态 | 问题 |
|------|------|------|
| 元数据 | {'✅' if report.get('metadata_ok') else '❌'} | {', '.join(report.get('metadata_issues', ['无'])[:2]) or '无'} |
| 文件结构 | {'✅' if report.get('structure_ok') else '❌'} | {', '.join(report.get('structure_issues', ['无'])[:2]) or '无'} |
| 代码质量 | {'✅' if report.get('code_ok') else '⚠️'} | {', '.join(report.get('code_issues', ['无'])[:2]) or '无'} |
| 自我感知 | {'✅' if report.get('self_aware') else '❌'} | {', '.join(report.get('self_aware_issues', ['无'])[:2]) or '无'} |
| 边界完整性 | {'✅' if report.get('boundary_ok') else '❌'} | {', '.join(report.get('boundary_issues', ['无'])[:2]) or '无'} |

## P0 问题（必须修复）

{p0_text or '无'}

## P1 问题（建议修复）

{p1_text or '无'}
"""

    report_file.write_text(content, encoding="utf-8")
    return str(report_file)


def _build_manual_inline(skill_name: str, scan: dict, report: dict) -> str:
    """生成 manual.md（inline fallback 模式）"""
    skill_md = scan["files"].get("SKILL.md", "")
    skill_py = scan["files"].get("skill.py", "")

    # 从 SKILL.md 提取 description
    desc_match = re.search(r"description\s*[=:]\s*['\"](.+?)['\"]", skill_md)
    description = desc_match.group(1) if desc_match else "（无描述）"

    # 提取 triggers
    triggers = re.findall(r"[「'\"](.+?)[」'\"]", skill_md)

    # 提取 actions
    actions = [a.strip() for a in re.findall(r"`?\b(critique|clear|health|search|store|hybrid|stats|capture|inject|archive|check|confirm|deny)\b`?", skill_py, re.I)]

    p0_issues = [f["issue"] for f in report.get("p0_fixes", [])]
    p1_issues = [f["issue"] for f in report.get("p1_fixes", [])]

    return f"""# {skill_name} 使用手册

## 一句话定位
{description}

## 你能做什么操作

| 你说什么 | 系统做什么 |
|---------|-----------|
| `锐评一下 {skill_name}` | 扫描 skill，跑独立 critique，生成 critique.md + manual.md |
| `锐评 {skill_name}` | 同上 |
| `critique {skill_name}` | 同上 |

## 它依赖什么

- **OpenClaw sessions_spawn**：独立 session 跑锐评（防止自我美化）
- **workspace 文件系统**：读写 skills/{skill_name}/ 目录

## 已知问题

### P0（必须修复）
{chr(10).join(f'- {i}' for i in p0_issues) if p0_issues else '无'}

### P1（建议修复）
{chr(10).join(f'- {i}' for i in p1_issues) if p1_issues else '无'}

## 状态检查

| 你说什么 | 返回 |
|---------|------|
| `critique action=health` | skill 自检，目录是否可读 |

---
*此手册由锐评系统自动生成（inline fallback 模式）*
"""


def run_critique(skill_name: str, rubric_result: dict = None, use_subagent: bool = True) -> dict:
    """运行完整锐评流程（融合版）"""
    # 1. 扫描
    scan = _scan_skill(skill_name)
    if not scan["exists"]:
        return {"error": f"skill 目录不存在：skills/{skill_name}/"}

    # 2. 构建 prompt（融合 rubric 评分）
    prompt = _build_critique_prompt(skill_name, scan, rubric_result)

    # 3. 尝试 spawn 独立 subagent
    if use_subagent:
        try:
            return {
                "ok": True,
                "skill_name": skill_name,
                "status": "spawn_requested",
                "prompt": prompt[:200] + "...",
                "note": "请使用你的 agent 框架的 subagent 能力运行此 prompt"
            }
        except Exception:
            pass

    # 4. Inline fallback：写骨架报告
    skeleton_report = {
        "metadata_ok": True,
        "metadata_issues": ["（需 LLM 填充，建议用 subagent 重新跑）"],
        "structure_ok": True,
        "structure_issues": [],
        "code_ok": True,
        "code_issues": [],
        "self_aware": False,
        "self_aware_issues": ["subagent 不可用，未完成 LLM 评估"],
        "boundary_ok": True,
        "boundary_issues": [],
        "overall_score": 0,
        "p0_fixes": [],
        "p1_fixes": [],
    }
    critique_path = _write_critique_report(skill_name, skeleton_report)

    # 写 manual.md
    manual_content = _build_manual_inline(skill_name, scan, skeleton_report)
    manual_path = SKILL_ROOT / skill_name / "manual.md"
    manual_path.write_text(manual_content, encoding="utf-8")

    return {
        "ok": True,
        "skill_name": skill_name,
        "status": "inline_skeleton",
        "critique_path": critique_path,
        "manual_path": str(manual_path),
        "note": "subagent 不可用，已写入手册和骨架报告。完整锐评需手动触发 subagent。"
    }


def clear_critique(skill_name: str) -> dict:
    """删除锐评报告"""
    skill_dir = SKILL_ROOT / skill_name
    removed = []
    for f in ["critique.md", "manual.md"]:
        fp = skill_dir / f
        if fp.exists():
            fp.unlink()
            removed.append(f)
    if removed:
        return {"ok": True, "removed": removed}
    return {"ok": True, "message": "无报告需要删除"}


def health_check() -> dict:
    """自检"""
    readable = []
    broken = []
    if SKILL_ROOT.exists():
        for d in SKILL_ROOT.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                try:
                    list(d.iterdir())
                    readable.append(d.name)
                except Exception:
                    broken.append(d.name)
    return {
        "ok": True,
        "readable_count": len(readable),
        "broken": broken,
        "total": len(readable) + len(broken),
    }


if __name__ == "__main__":
    import sys
    import os

    if len(sys.argv) < 2:
        print("Usage: critique.py <skill_name> [--clear|--health]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "--health":
        print(json.dumps(health_check(), ensure_ascii=False, indent=2))
    elif cmd == "--clear":
        skill_name = sys.argv[2] if len(sys.argv) > 2 else ""
        print(json.dumps(clear_critique(skill_name), ensure_ascii=False, indent=2))
    else:
        skill_name = cmd
        result = run_critique(skill_name)
        print(json.dumps(result, ensure_ascii=False, indent=2))
