"""Tests for enrichment functionality in the workspace."""

from __future__ import annotations

import pytest

from flora.ui.handlers import workspace
from flora.ui.server import create_app


@pytest.fixture()
def state(tmp_path):
    _, _, st = create_app(workdir=tmp_path)
    # Create a minimal dataset for testing
    st.db.execute("CREATE TABLE samples (sample_id TEXT PRIMARY KEY, biome TEXT)")
    st.db.execute("CREATE TABLE asv (sample_id TEXT, feature_id TEXT, abundance INTEGER)")
    st.db.execute("CREATE TABLE taxonomy (feature_id TEXT PRIMARY KEY, genus TEXT)")
    
    # Insert test data
    st.db.execute("INSERT INTO samples VALUES ('S001', 'Amazon'), ('S002', 'Atlantic_Forest')")
    st.db.execute("INSERT INTO asv VALUES ('S001', 'f1', 100), ('S001', 'f2', 50), ('S002', 'f1', 75)")
    st.db.execute("INSERT INTO taxonomy VALUES ('f1', 'Bacteria'), ('f2', 'Archaea')")
    
    return st


def test_enrichment_functionality(state):
    """Test that enrichment functionality works correctly."""
    # Test basic enrichment functionality
    data = workspace.explore_summary(state, {"rank": ["genus"]})
    
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