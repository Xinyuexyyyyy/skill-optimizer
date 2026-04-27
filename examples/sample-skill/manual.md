# /tmp/openclaw/skill-optimizer-open/examples/sample-skill 使用手册

## 一句话定位
（无描述）

## 你能做什么操作

| 你说什么 | 系统做什么 |
|---------|-----------|
| `锐评一下 /tmp/openclaw/skill-optimizer-open/examples/sample-skill` | 扫描 skill，跑独立 critique，生成 critique.md + manual.md |
| `锐评 /tmp/openclaw/skill-optimizer-open/examples/sample-skill` | 同上 |
| `critique /tmp/openclaw/skill-optimizer-open/examples/sample-skill` | 同上 |

## 它依赖什么

- **OpenClaw sessions_spawn**：独立 session 跑锐评（防止自我美化）
- **workspace 文件系统**：读写 skills//tmp/openclaw/skill-optimizer-open/examples/sample-skill/ 目录

## 已知问题

### P0（必须修复）
无

### P1（建议修复）
无

## 状态检查

| 你说什么 | 返回 |
|---------|------|
| `critique action=health` | skill 自检，目录是否可读 |

---
*此手册由锐评系统自动生成（inline fallback 模式）*
