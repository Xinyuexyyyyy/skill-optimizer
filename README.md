# Skill Optimizer

> AI-powered SKILL.md evaluation and optimization system with critique integration.

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## What is this?

**Skill Optimizer** evaluates and automatically improves AI skill definitions (SKILL.md files). It combines:

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

## Workflow

```
User: skill-optimizer optimize my-skill
    ↓
Phase 1: 8-dimension scoring (rubric.py)
    ↓
Phase 2: Deep critique (critique.py)
    - Scan skill directory
    - Generate critique.md (P0/P1/P2 issues)
    - Generate manual.md (user manual)
    ↓
Phase 3: Smart optimization (optimizer.py)
    - Target lowest dimension
    - Incorporate critique issues
    - Ratchet: keep if score ↑, rollback if ≤
    ↓
Phase 4: Verification
    - Re-score
    - Check if issues fixed
```

## Ratchet Mechanism

The optimizer only keeps changes that **improve the score**:

1. Snapshot current version
2. Generate improvement for lowest dimension
3. Re-score
4. **If score ↑ → keep** | **If score ≤ → rollback**
5. Skip dimensions that fail 2 times in a row

### Example Output

```bash
$ skill-optimizer optimize feedback

[optimizer] Baseline: 48/100
  Frontmatter: 5/8 — name规范; description缺少触发词
  Workflow: 8/15 — 步骤数:21; 输入输出一般(2)
  Boundary: 0/10 — OK
  ...

[optimizer] === Round 1 ===
[optimizer] Lowest: Boundary (0/10)
[optimizer] Snapshot saved
[optimizer] Change: boundary section added
[optimizer] Score: 48 → 52
[optimizer] ✅ Keep improvement

[optimizer] === Round 2 ===
[optimizer] Lowest: Checkpoint (0/7)
...
```

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
│   └── test_rubric.py # Unit tests
└── examples/
    └── sample-skill/
        └── SKILL.md   # Example skill
```

## API Usage

```python
from skill_optimizer.rubric import score_skill
from skill_optimizer.critique import run_critique
from skill_optimizer.optimizer import run_optimization

# Score a skill
result = score_skill("my-skill")
print(f"Total: {result['total']}/100")

# Critique
result = run_critique("my-skill")
print(f"Report: {result['critique_path']}")

# Optimize
result = run_optimization("my-skill", max_rounds=3)
print(f"Final: {result['final_score']}/100")
```

## Testing

```bash
# Run tests
python -m pytest tests/

# Test with sample skill
skill-optimizer score examples/sample-skill
```

## License

MIT — see [LICENSE](LICENSE)

## Contributing

1. Fork the repo
2. Create a branch: `git checkout -b feature-name`
3. Make changes
4. Run tests: `python -m pytest`
5. Submit PR

## Changelog

### v1.0.0 (2026-04-27)
- Initial release
- 8-dimension scoring engine
- Ratchet optimization mechanism
- Deep critique integration
- CLI interface