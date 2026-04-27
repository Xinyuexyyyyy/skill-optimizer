#!/usr/bin/env python3
"""
skill-optimizer — 统一入口（开源版）

融合 skill-optimizer + critique 能力：
  score           → rubric.py（8维评分）
  critique        → critique.py（深度锐评）
  optimize        → optimizer.py（优化循环+棘轮，前置自动跑 critique）
  score_execution → scorer（内联）+ execution_logger（L1自动）
  snapshot_*      → snapshot（内联）
  reflect         → execution_logger L2反思
  log_manual      → execution_logger 手动记录

自动日志：每次 action 调用都会记录到 logs/executions/
"""
import os
import sys
import json
import shutil
import subprocess
import re
from pathlib import Path
from datetime import datetime

# ── 配置加载 ────────────────────────────────────────────
SKILL_ROOT = os.environ.get("SKILL_ROOT", str(Path.home() / ".openclaw" / "workspace" / "skills"))
DASHSCOPE_KEY = os.environ.get("DASHSCOPE_API_KEY", "")
MODEL = os.environ.get("SKILL_OPTIMIZER_MODEL", "qwen3.5-flash")
WEBHOOK_URL = os.environ.get("SKILL_OPTIMIZER_WEBHOOK", "")

# ── 清除代理 ────────────────────────────────────────────
for _k in list(os.environ.keys()):
    if "proxy" in _k.lower() or _k.upper() in (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"
    ):
        del os.environ[_k]

SKILL_DIR = Path(__file__).parent

# ── Scorer 内联（来自 skill-scorer） ───────────────────

SCORES_DB = Path.home() / ".openclaw" / "skill-eval" / "scores.db"
SCORES_DB.parent.mkdir(parents=True, exist_ok=True)

def get_db():
    import sqlite3
    conn = sqlite3.connect(str(SCORES_DB))
    conn.execute("""
        CREATE TABLE IF NOT EXISTS skill_scores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skill_name TEXT NOT NULL,
            version TEXT NOT NULL,
            overall REAL NOT NULL,
            accuracy REAL,
            efficiency REAL,
            execution_time_ms INTEGER,
            token_used INTEGER,
            scored_at TEXT NOT NULL,
            note TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill ON skill_scores(skill_name, scored_at)")
    return conn

def infer_accuracy(result) -> float:
    if isinstance(result, dict):
        if result.get("ok"):
            return 100.0
        err = str(result.get("error", ""))
        if "timeout" in err.lower():
            return 30.0
        if "not found" in err.lower():
            return 40.0
        return 60.0
    return 70.0

def infer_efficiency(time_ms: int, tokens: int = 0) -> float:
    if time_ms <= 0:
        return 70.0
    time_score = min(100, 5000 / time_ms * 100)
    if tokens > 0:
        token_score = min(100, 5000 / tokens * 100)
        return (time_score * 0.5 + token_score * 0.5)
    return time_score

def score_execution(skill_name: str, result=None, time_ms: int = 0, tokens: int = 0, note: str = "") -> dict:
    """执行后评分"""
    import sqlite3
    if not skill_name:
        return {"error": "skill_name required"}
    accuracy = infer_accuracy(result) if result else None
    efficiency = infer_efficiency(time_ms, tokens) if time_ms > 0 else None
    overall = (accuracy or 70) * 0.6 + (efficiency or 70) * 0.4
    overall = round(min(100, max(0, overall)), 1)
    try:
        conn = get_db()
        version = _get_version(skill_name)
        now = datetime.utcnow().isoformat()
        conn.execute("""
            INSERT INTO skill_scores (skill_name, version, overall, accuracy, efficiency, execution_time_ms, token_used, scored_at, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (skill_name, version, overall, accuracy, efficiency, time_ms or None, tokens or None, now, note))
        conn.commit()
        cur = conn.execute("SELECT AVG(overall), COUNT(*) FROM skill_scores WHERE skill_name = ?", (skill_name,))
        avg, cnt = cur.fetchone()
        conn.close()
        return {"ok": True, "skill": skill_name, "overall": overall, "avg": round(avg, 1), "count": cnt}
    except Exception as e:
        return {"error": str(e)}

def _get_version(skill_name: str) -> str:
    """检测 skill 版本"""
    candidates = [
        Path(SKILL_ROOT) / skill_name,
    ]
    for sp in candidates:
        if not sp.exists():
            continue
        pkg = sp / "package.json"
        if pkg.exists():
            try:
                v = json.loads(pkg.read_text()).get("version", "")
                if v:
                    return v
            except:
                pass
        sk = sp / "SKILL.md"
        if sk.exists():
            m = re.search(r'version:\s*"?(\S+)"?', sk.read_text())
            if m:
                return m.group(1)
    return "untagged"

def list_scores(skill_name: str = "") -> dict:
    """列出评分历史"""
    import sqlite3
    if not skill_name:
        return {"error": "skill_name required"}
    try:
        conn = get_db()
        rows = conn.execute("""
            SELECT skill_name, version, overall, accuracy, efficiency, execution_time_ms, scored_at, note
            FROM skill_scores WHERE skill_name = ? ORDER BY scored_at DESC LIMIT 20
        """, (skill_name,)).fetchall()
        conn.close()
        return {
            "ok": True, "skill": skill_name, "count": len(rows),
            "scores": [{"version": r[1], "overall": r[2], "accuracy": r[3], "efficiency": r[4],
                        "time_ms": r[5], "at": r[6], "note": r[7]} for r in rows]
        }
    except Exception as e:
        return {"error": str(e)}

def get_stats(skill_name: str = "") -> dict:
    """评分统计"""
    import sqlite3
    if not skill_name:
        # 返回所有 skill 概览
        try:
            conn = get_db()
            rows = conn.execute("""
                SELECT skill_name, AVG(overall), MAX(overall), MIN(overall), COUNT(*)
                FROM skill_scores GROUP BY skill_name
            """).fetchall()
            conn.close()
            return {"ok": True, "skills": [
                {"skill": r[0], "avg": round(r[1], 1), "max": r[2], "min": r[3], "count": r[4]}
                for r in rows
            ]}
        except Exception as e:
            return {"error": str(e)}
    try:
        conn = get_db()
        row = conn.execute("""
            SELECT AVG(overall), MIN(overall), MAX(overall), COUNT(*), AVG(accuracy), AVG(efficiency)
            FROM skill_scores WHERE skill_name = ?
        """, (skill_name,)).fetchone()
        conn.close()
        if row[3] == 0:
            return {"ok": True, "skill": skill_name, "total": 0}
        return {
            "ok": True, "skill": skill_name,
            "avg_overall": round(row[0], 1) if row[0] else None,
            "min": row[1], "max": row[2], "total": row[3],
            "avg_accuracy": round(row[4], 1) if row[4] else None,
            "avg_efficiency": round(row[5], 1) if row[5] else None,
        }
    except Exception as e:
        return {"error": str(e)}

# ── Snapshot 内联（来自 agent-snapshot） ────────────────

SNAPSHOT_BASE = Path.home() / ".openclaw" / "snapshots"

def snapshot_export(skill_name: str = "") -> dict:
    """导出快照"""
    if not skill_name:
        # 列出所有 skills
        skills_dir = Path(SKILL_ROOT)
        names = []
        if skills_dir.exists():
            for sub in skills_dir.iterdir():
                if sub.is_dir() and (sub / "SKILL.md").exists():
                    names.append(sub.name)
        return {"ok": True, "skills": sorted(names)}

    candidates = [
        Path(SKILL_ROOT) / skill_name,
    ]
    skill_dir = None
    for d in candidates:
        if d.exists():
            skill_dir = d
            break

    if not skill_dir:
        return {"error": f"Skill not found: {skill_name}"}

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    snap_dir = SNAPSHOT_BASE / "skills" / skill_name / f"{ts}"
    snap_dir.mkdir(parents=True, exist_ok=True)

    for fname in ["SKILL.md", "skill.py", "skill.js"]:
        src = skill_dir / fname
        if src.exists():
            shutil.copy2(src, snap_dir / fname)

    # 快照列表（保留最近7个）
    all_snaps = sorted((SNAPSHOT_BASE / "skills" / skill_name).iterdir(), reverse=True)
    for old in all_snaps[7:]:
        shutil.rmtree(old)

    return {"ok": True, "skill": skill_name, "snapshot": str(snap_dir), "files": [f.name for f in snap_dir.iterdir()]}

def snapshot_restore(skill_name: str, snapshot_path: str = "") -> dict:
    """从快照恢复"""
    snap_base = SNAPSHOT_BASE / "skills" / skill_name
    if not snapshot_path:
        # 取最新的
        snaps = sorted(snap_base.iterdir(), reverse=True)
        if not snaps:
            return {"error": f"No snapshots found for: {skill_name}"}
        snap_dir = snaps[0]
    else:
        snap_dir = Path(snapshot_path)
        if not snap_dir.exists():
            return {"error": f"Snapshot not found: {snapshot_path}"}

    candidates = [
        Path(SKILL_ROOT) / skill_name,
    ]
    skill_dir = None
    for d in candidates:
        if d.exists():
            skill_dir = d
            break

    if not skill_dir:
        return {"error": f"Skill not found: {skill_name}"}

    for fname in ["SKILL.md", "skill.py", "skill.js"]:
        src = snap_dir / fname
        if src.exists():
            shutil.copy2(src, skill_dir / fname)

    return {"ok": True, "skill": skill_name, "restored_from": str(snap_dir)}

def snapshot_diff(snap1: str, snap2: str) -> dict:
    """对比两个快照"""
    p1 = Path(snap1) / "SKILL.md"
    p2 = Path(snap2) / "SKILL.md"
    if not p1.exists():
        return {"error": f"Snapshot not found: {snap1}"}
    if not p2.exists():
        return {"error": f"Snapshot not found: {snap2}"}

    lines1 = p1.read_text(encoding="utf-8").splitlines()
    lines2 = p2.read_text(encoding="utf-8").splitlines()

    # 简单统计
    return {
        "ok": True,
        "snap1": str(p1),
        "snap2": str(p2),
        "snap1_lines": len(lines1),
        "snap2_lines": len(lines2),
        "diff_hint": "run 'diff' command to see detailed diff"
    }

# ── Critique 整合（来自 critique/skill.py） ─────────────

def _scan_skill(skill_name: str) -> dict:
    """扫描 skill 目录，返回文件列表和关键内容"""
    skill_dir = Path(SKILL_ROOT) / skill_name
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
    """构建发给 subagent 的完整锐评 prompt（融合 rubric 评分）"""
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
# {skill中文名} 使用手册

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
    skill_dir = Path(SKILL_ROOT) / skill_name
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
    desc_match = re.search(r"description\s*[=:]\s*["'](.+?)["']", skill_md)
    description = desc_match.group(1) if desc_match else "（无描述）"

    # 提取 triggers
    triggers = re.findall(r"[「"'](.+?)[」"']", skill_md)

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
            # 注意：这里依赖外部 sessions_spawn 能力
            # 开源版中改为可选依赖，不可用则 fallback inline
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
    manual_path = Path(SKILL_ROOT) / skill_name / "manual.md"
    manual_path.write_text(manual_content, encoding="utf-8")

    return {
        "ok": True,
        "skill_name": skill_name,
        "status": "inline_skeleton",
        "critique_path": critique_path,
        "manual_path": str(manual_path),
        "note": "subagent 不可用，已写入手册和骨架报告。完整锐评需手动触发 subagent。"
    }


# ── Rubric + Optimizer 代理 ────────────────────────────

def call_rubric(skill_name: str, test_prompts: list = None) -> dict:
    """调用 rubric.py"""
    sys.path.insert(0, str(SKILL_DIR))
    from rubric import score_skill
    return score_skill(
        skill_name,
        test_prompts=test_prompts,
        dashscope_key=DASHSCOPE_KEY,
        model=MODEL,
        skill_root=SKILL_ROOT,
    )

def call_optimizer(skill_name: str, test_prompts: list = None, max_rounds: int = 3, auto_confirm: bool = False, rubric_result: dict = None) -> dict:
    """调用 optimizer.py（融合 critique 信息）"""
    sys.path.insert(0, str(SKILL_DIR))
    from optimizer import run_optimization
    return run_optimization(
        skill_name,
        test_prompts=test_prompts,
        max_rounds=max_rounds,
        auto_confirm=auto_confirm,
        dashscope_key=DASHSCOPE_KEY,
        model=MODEL,
        skill_root=SKILL_ROOT,
        rubric_result=rubric_result,
    )

# ── 主入口 ──────────────────────────────────────────────

def handle(action: str, params: dict) -> dict:
    # 导入放在函数内避免循环依赖
    import sys, time as time_module
    sys.path.insert(0, str(Path(__file__).parent))
    from execution_logger import log, reflect as el_reflect, log_manual

    skill_name = params.get("skill_name", "skill-optimizer")
    start = time_module.time()

    try:
        result = _dispatch(action, params)
        duration_ms = int((time_module.time() - start) * 1000)

        # 自动 L1 日志
        result_str = "ok" if result.get("ok") or result.get("error") is None else "error"
        error_str = result.get("error") if result.get("error") else None

        log(
            skill=skill_name,
            action=action,
            result=result_str,
            duration_ms=duration_ms,
            error=error_str,
            session="main",
        )

        return result

    except Exception as e:
        duration_ms = int((time_module.time() - start) * 1000)
        log(
            skill=skill_name,
            action=action,
            result="error",
            duration_ms=duration_ms,
            error=str(e),
        )
        return {"error": str(e)}


def _dispatch(action: str, params: dict) -> dict:
    if action == "score":
        return call_rubric(
            params.get("skill_name", ""),
            params.get("test_prompts"),
        )

    elif action == "critique":
        # 先评分，再锐评
        skill_name = params.get("skill_name", "")
        rubric_result = None
        if params.get("include_score", True):
            rubric_result = call_rubric(skill_name)
        return run_critique(
            skill_name,
            rubric_result=rubric_result,
            use_subagent=params.get("use_subagent", True),
        )

    elif action == "optimize":
        # 优化循环（融合 critique）
        skill_name = params.get("skill_name", "")
        
        # Phase 1: 评分
        rubric_result = call_rubric(skill_name, params.get("test_prompts"))
        
        # Phase 2: 锐评（可选）
        critique_result = None
        if params.get("include_critique", True):
            critique_result = run_critique(skill_name, rubric_result=rubric_result, use_subagent=False)
        
        # Phase 3: 优化
        return call_optimizer(
            skill_name,
            test_prompts=params.get("test_prompts"),
            max_rounds=params.get("max_rounds", 3),
            auto_confirm=params.get("auto_confirm", False),
            rubric_result=rubric_result,
        )

    elif action == "score_execution":
        return score_execution(
            params.get("skill_name", ""),
            params.get("result"),
            params.get("execution_time_ms", 0),
            params.get("token_used", 0),
            params.get("note", ""),
        )

    elif action == "snapshot_export":
        return snapshot_export(params.get("skill_name", ""))

    elif action == "snapshot_restore":
        return snapshot_restore(
            params.get("skill_name", ""),
            params.get("snapshot_path", ""),
        )

    elif action == "snapshot_diff":
        return snapshot_diff(
            params.get("snap1", ""),
            params.get("snap2", ""),
        )

    elif action == "stats":
        return get_stats(params.get("skill_name", ""))

    elif action == "list":
        return snapshot_export("")

    elif action == "scores_list":
        return list_scores(params.get("skill_name", ""))

    elif action == "reflect":
        # L2 反思
        sys.path.insert(0, str(Path(__file__).parent))
        from execution_logger import reflect as el_reflect
        return el_reflect(
            params.get("execution_id", ""),
            problem=params.get("problem"),
            root_cause=params.get("root_cause"),
            solution=params.get("solution"),
            avoid=params.get("avoid"),
            optimize=params.get("optimize"),
        )

    elif action == "log_manual":
        sys.path.insert(0, str(Path(__file__).parent))
        from execution_logger import log_manual
        return {"ok": True, "id": log_manual(
            skill=params.get("skill", "unknown"),
            action=params.get("action", ""),
            result=params.get("result", "ok"),
            problem=params.get("problem"),
            root_cause=params.get("root_cause"),
            solution=params.get("solution"),
            avoid=params.get("avoid"),
            optimize=params.get("optimize"),
            duration_ms=params.get("duration_ms", 0),
            tokens_used=params.get("tokens_used", 0),
            error=params.get("error"),
        )}

    else:
        return {"error": f"Unknown action: {action}"}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: skill.py <action> [params_json]")
        sys.exit(1)

    action = sys.argv[1]
    params = json.loads(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2] else {}

    result = handle(action, params)
    print(json.dumps(result, ensure_ascii=False, indent=2))
