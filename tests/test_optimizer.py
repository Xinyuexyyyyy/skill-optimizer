import pytest
import sys
import os
import json
import tempfile
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from rubric import score_skill
from critique import run_critique, clear_critique, health_check, _scan_skill
from optimizer import run_optimization, get_status, snapshot, load_results


class TestRubric:
    """Test 8-dimension scoring engine"""
    
    def test_score_sample_skill(self):
        result = score_skill("examples/sample-skill/SKILL.md")
        assert "skill" in result
        assert "total" in result
        assert len(result["dimensions"]) == 8
        assert result["structure_score"] > 0
        assert result["effectiveness_score"] >= 10
    
    def test_score_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            score_skill("nonexistent-skill")
    
    def test_dimensions_structure(self):
        result = score_skill("examples/sample-skill/SKILL.md")
        for d in result["dimensions"]:
            assert "name" in d
            assert "label" in d
            assert "score" in d
            assert "max" in d
            assert "reason" in d
            assert d["score"] <= d["max"]


class TestCritique:
    """Test critique functionality"""
    
    def test_scan_skill(self):
        scan = _scan_skill("examples/sample-skill")
        assert scan["exists"] is True
        assert "SKILL.md" in scan["files"]
    
    def test_scan_nonexistent(self):
        scan = _scan_skill("nonexistent")
        assert scan["exists"] is False
    
    def test_run_critique_inline(self):
        result = run_critique("examples/sample-skill", use_subagent=False)
        assert result["ok"] is True
        assert result["status"] == "inline_skeleton"
        assert "critique_path" in result
        assert "manual_path" in result
    
    def test_clear_critique(self):
        # First create a dummy critique
        skill_dir = Path("examples/sample-skill")
        (skill_dir / "critique.md").write_text("test")
        
        result = clear_critique("examples/sample-skill")
        assert result["ok"] is True
        assert "critique.md" in result["removed"]
    
    def test_health_check(self):
        result = health_check()
        assert result["ok"] is True
        assert "readable_count" in result


class TestOptimizer:
    """Test optimization loop and ratchet mechanism"""
    
    def test_snapshot_creation(self):
        snap_dir = snapshot("examples/sample-skill")
        assert snap_dir.exists()
        assert (snap_dir / "SKILL.md").exists()
    
    def test_load_results_new_skill(self):
        results = load_results("test-new-skill-12345")
        assert results["skill"] == "test-new-skill-12345"
        assert results["baseline"] is None
        assert results["rounds"] == []
    
    def test_get_status_empty(self):
        result = get_status("nonexistent-skill-12345")
        assert result["has_baseline"] is False
        assert result["current_score"] == 0
    
    def test_get_status_all(self):
        result = get_status()
        assert "skills" in result
        assert "total" in result


class TestIntegration:
    """Integration tests"""
    
    def test_full_pipeline(self):
        """Test score -> critique -> optimize pipeline"""
        # Score
        score_result = score_skill("examples/sample-skill")
        assert score_result["total"] > 0
        
        # Critique
        critique_result = run_critique("examples/sample-skill", rubric_result=score_result, use_subagent=False)
        assert critique_result["ok"] is True
        
        # Verify files created
        skill_dir = Path("examples/sample-skill")
        assert (skill_dir / "critique.md").exists()
        assert (skill_dir / "manual.md").exists()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
