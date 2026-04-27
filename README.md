# Skill Optimizer

> AI-powered SKILL.md evaluation and optimization system with critique integration.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## What is this?

**Skill Optimizer** is a tool that evaluates and automatically improves AI skill definitions (SKILL.md files). It combines:

- **8-dimension scoring** (structure + effectiveness)
- **Deep critique** (P0/P1/P2 issue lists + user manuals)
- **Automatic optimization** with ratchet mechanism (only keep improvements)

## Quick Start

```bash
# Install
pip install skill-optimizer

# Set your API key
export DASHSCOPE_API_KEY=your_key_here

# Evaluate a skill
skill-optimizer score my-skill

# Full critique (score + deep analysis)
skill-optimizer critique my-skill

# Optimize (score + critique + auto-improve)
skill-optimizer optimize my-skill
```

## 8-Dimension Scoring

| Dimension | Weight | What it checks |
|-----------|--------|----------------|
| Frontmatter | 8 | Name format, description quality |
| Workflow | 15 | Step clarity, input/output specs |
| Boundary | 10 | Error handling, timeouts, fallbacks |
| Checkpoint | 7 | User confirmation points |
| Specificity | 15 | Examples, concrete parameters |
| Resources | 5 | File references, dependencies |
| Architecture | 15 | Structure, no redundancy |
| Effectiveness | 25 | Real test prompt performance |

## Ratchet Mechanism

The optimizer only keeps changes that **improve the score**:

1. Snapshot current version
2. Generate improvement for lowest dimension
3. Re-score
4. **If score ↑ → keep** | **If score ≤ → rollback**
5. Skip dimensions that fail 2 times in a row

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `SKILL_ROOT` | `~/.openclaw/workspace/skills` | Skill directory |
| `DASHSCOPE_API_KEY` | *(required)* | API key for LLM calls |
| `SKILL_OPTIMIZER_MODEL` | `qwen3.5-flash` | Model name |
| `SKILL_OPTIMIZER_WEBHOOK` | *(optional)* | Notification webhook |

## Project Structure

```
skill-optimizer/
├── src/
│   ├── skill.py       # Main entry point
│   ├── rubric.py      # 8-dimension scoring engine
│   ├── optimizer.py   # Optimization loop + ratchet
│   ├── critique.py    # Deep critique + manual generation
│   ├── snapshot.py    # Version snapshots
│   ├── scorer.py      # Execution scoring
│   └── cli.py         # Command line interface
├── tests/
└── examples/
```

## License

MIT — see [LICENSE](LICENSE)
