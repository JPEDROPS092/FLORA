"""Tests for grouping functionality in the workspace."""

from __future__ import annotations

import pytest

from flora.ui.handlers import workspace
from flora.ui.server import create_app


@pytest.fixture()
def state(tmp_path):
    _, _, st = create_app(workdir=tmp_path)
    st.db.execute(
        "INSERT INTO samples (sample_id, biome) VALUES ('S001', 'Amazon'), ('S002', 'Atlantic_Forest'), ('S003', 'Amazon')"
    )
    st.db.execute(
        "INSERT INTO sample_metadata VALUES ('S001','site','Site1'), ('S002','site','Site1'), ('S003','site','Site2')"
    )
    st.db.execute(
        "INSERT INTO asv (sample_id, feature_id, abundance) VALUES "
        "('S001', 'f1', 100), ('S001', 'f2', 50), ('S002', 'f1', 75), ('S003', 'f2', 120)"
    )
    st.db.execute("INSERT INTO taxonomy (feature_id, genus) VALUES ('f1', 'Bacteria'), ('f2', 'Archaea')")
    
    return st


def test_group_by_functionality(state):
    """Test that group_by parameter works correctly."""
    # Test with biome grouping
    data = workspace.explore_summary(state, {"group_by": ["biome"], "rank": ["genus"]})
    
    # Verify we get expected structure
    assert "sample_count" in data
    assert "asv_count" in data
    assert "tree" in data
    assert "comparisons" in data
    assert "differential" in data


def test_default_group_functionality(state):
    """Test that default group functionality works correctly."""
    from flora.ui.handlers.workspace import _default_group
    
    group = _default_group(state.db)
    # Should return a valid group name or default
    assert isinstance(group, str)


def test_groups_frame_functionality(state):
    """Test the _groups_frame function directly."""
    from flora.ui.handlers.workspace import _groups_frame
    
    # Test with a valid group column
    frame = _groups_frame(state.db, "biome")
    assert "sample_id" in frame.columns
    assert "group" in frame.columns
    
    # Test with invalid group column
    frame = _groups_frame(state.db, "nonexistent")
    assert len(frame) == 0


def test_group_by_with_different_columns(state):
    """Test group_by with different column types."""
    # Test with site grouping
    data = workspace.explore_summary(state, {"group_by": ["site"], "rank": ["genus"]})
    
    # Verify we get expected structure
    assert "sample_count" in data
    assert "asv_count" in data
    assert "tree" in data
    assert "comparisons" in data
    assert "differential" in data