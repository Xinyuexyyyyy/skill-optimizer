import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rubric import (
    score_frontmatter,
    score_workflow,
    score_boundary,
    score_checkpoint,
    score_specificity,
    score_resources,
    score_architecture,
    score_skill,
)


class TestFrontmatter:
    def test_perfect_frontmatter(self):
        fm = {"name": "my-skill", "description": "当用户说hello时使用"}
        body = ""
        score, reason = score_frontmatter(fm, body)
        assert score == 8
        assert "name规范" in reason
        assert "触发词" in reason

    def test_bad_name(self):
        fm = {"name": "MySkill", "description": "当用户使用"}
        score, reason = score_frontmatter(fm, body="")
        assert score < 8
        assert "name格式" in reason

    def test_long_description(self):
        fm = {"name": "my-skill", "description": "x" * 1025}
        score, reason = score_frontmatter(fm, body="")
        assert score < 8
        assert "过长" in reason


class TestWorkflow:
    def test_good_workflow(self):
        body = """
## Workflow

1. Parse input
   - Input: user message
   - Output: parsed intent

2. Execute
   - Input: parsed intent
   - Output: result

3. Format
   - Input: result
   - Output: response
"""
        score, reason = score_workflow(body)
        assert score >= 6
        assert "步骤数" in reason

    def test_no_steps(self):
        body = "Just some text without steps"
        score, reason = score_workflow(body)
        assert score < 5


class TestBoundary:
    def test_good_boundary(self):
        body = """
## Boundary

- If file not found, return error
- Timeout after 30 seconds
- Fallback to default
- Handle API errors
"""
        score, reason = score_boundary(body)
        assert score >= 6
        assert "边界覆盖" in reason

    def test_no_boundary(self):
        body = "No boundary conditions here"
        score, reason = score_boundary(body)
        assert score == 0


class TestCheckpoint:
    def test_good_checkpoint(self):
        body = """
- 操作前向用户确认
- 等用户回复后再继续
"""
        score, reason = score_checkpoint(body)
        assert score >= 5
        assert "检查点" in reason

    def test_no_checkpoint(self):
        body = "No checkpoints"
        score, reason = score_checkpoint(body)
        assert score <= 2


class TestSpecificity:
    def test_good_specificity(self):
        body = """
```bash
skill-optimizer score my-skill
```

```json
{"action": "score"}
```

Path: /tmp/test
API key: sk-xxx
"""
        score, reason = score_specificity(body)
        assert score >= 10
        assert "示例" in reason

    def test_vague_words(self):
        body = "使用等等、之类的参数"
        score, reason = score_specificity(body)
        assert score < 10
        assert "模糊词" in reason


class TestResources:
    def test_good_resources(self):
        body = """
- [link](http://example.com)
- `code reference`
- script: main.py
"""
        score, reason = score_resources(body)
        assert score >= 3
        assert "引用" in reason


class TestArchitecture:
    def test_good_architecture(self):
        body = """
## Overview
## Workflow
## Actions
## Boundary
"""
        score, reason = score_architecture(body)
        assert score >= 5
        assert "层次" in reason

    def test_too_long(self):
        body = "\n".join(["line"] * 600)
        score, reason = score_architecture(body)
        assert score < 10
        assert "过长" in reason


class TestIntegration:
    def test_score_sample_skill(self):
        result = score_skill("examples/sample-skill/SKILL.md")
        assert "skill" in result
        assert "total" in result
        assert "dimensions" in result
        assert len(result["dimensions"]) == 8
        assert result["structure_score"] > 0
        assert result["effectiveness_score"] >= 10

    def test_score_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            score_skill("nonexistent-skill")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
