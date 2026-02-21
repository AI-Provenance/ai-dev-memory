import os
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from devmemory.commands.install import (
    _install_skills_for_agent,
    _install_claude_skills,
    _install_antigravity_skills
)

def test_skill_files_are_valid():
    repo_skills_dir = Path(__file__).resolve().parent.parent / "devmemory" / "skills"
    assert repo_skills_dir.exists(), "Skills directory should exist"
    
    skill_dirs = [d for d in repo_skills_dir.iterdir() if d.is_dir()]
    assert len(skill_dirs) == 3, "Should have 3 skill directories"
    
    for skill_dir in skill_dirs:
        skill_file = skill_dir / "SKILL.md"
        assert skill_file.exists(), f"SKILL.md missing in {skill_dir.name}"
        
        content = skill_file.read_text()
        assert content.startswith("---"), "Should have YAML frontmatter"
        
        # very basic frontmatter check
        assert "name: " in content
        assert "description: " in content
        
        # Check there is content after frontmatter
        parts = content.split("---")
        assert len(parts) >= 3, "Frontmatter not properly closed"
        assert len(parts[2].strip()) > 0, "Body should not be empty"

def test_install_skills_for_agent(tmp_path):
    # Mock DevMemoryConfig so we can test substitution
    with patch("devmemory.commands.install.DevMemoryConfig.load") as mock_load:
        mock_config = MagicMock()
        mock_config.get_active_namespace.return_value = "test-namespace:123"
        mock_load.return_value = mock_config
        
        agent_dir = tmp_path / "skills"
        ok, count = _install_skills_for_agent(agent_dir)
        
        assert ok is True
        assert count == 3
        
        # DevMemory memory skill should have substitution
        mem_skill = agent_dir / "devmemory-memory" / "SKILL.md"
        assert mem_skill.exists()
        content = mem_skill.read_text()
        assert "test-namespace:123" in content
        assert "{{NAMESPACE}}" not in content
        
        # Run it again to test idempotency
        ok, count = _install_skills_for_agent(agent_dir)
        assert ok is True
        assert count == 3

def test_install_claude_skills(tmp_path):
    with patch("devmemory.commands.install.Path.home", return_value=tmp_path):
        with patch("devmemory.commands.install.DevMemoryConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.get_active_namespace.return_value = "default"
            mock_load.return_value = mock_config
            
            ok, count = _install_claude_skills()
            assert ok is True
            assert count == 3
            assert (tmp_path / ".claude" / "skills" / "devmemory-memory" / "SKILL.md").exists()
            assert (tmp_path / ".claude" / "skills" / "devmemory-context" / "SKILL.md").exists()
            assert (tmp_path / ".claude" / "skills" / "devmemory-coordination" / "SKILL.md").exists()

def test_install_antigravity_skills(tmp_path):
    with patch("devmemory.commands.install.Path.home", return_value=tmp_path):
        with patch("devmemory.commands.install.DevMemoryConfig.load") as mock_load:
            mock_config = MagicMock()
            mock_config.get_active_namespace.return_value = "default"
            mock_load.return_value = mock_config
            
            ok, count = _install_antigravity_skills()
            assert ok is True
            assert count == 3
            assert (tmp_path / ".gemini" / "antigravity" / "skills" / "devmemory-memory" / "SKILL.md").exists()
