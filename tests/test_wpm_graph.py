"""Tests for WPM trends graph controls."""

import sys
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, ".")

from ui.wpm_graph import WPMTimeSeriesGraph


@pytest.fixture(scope="module")
def app():
    """Provide a QApplication instance for graph tests."""
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def test_outlier_controls_update_marker_detection(app):
    """Relaxing the fence should suppress previously detected outliers."""
    graph = WPMTimeSeriesGraph()
    graph.update_graph(
        ([48, 49, 50, 50, 51, 51, 52, 52, 90], list(range(1, 10)), list(range(101, 110)))
    )

    assert graph.current_outlier_indices == [8]
    assert graph.delete_outliers_button.isEnabled()

    graph.outlier_fence_spin.setValue(5.0)

    assert graph.current_outlier_indices == []
    assert not graph.delete_outliers_button.isEnabled()


def test_delete_outliers_emits_burst_ids(app):
    """Deleting outliers should pass burst IDs, not just display positions."""
    graph = WPMTimeSeriesGraph()
    callback = Mock()
    graph.set_delete_outliers_callback(callback)
    graph.update_graph(
        ([48, 49, 50, 50, 51, 51, 52, 52, 90], list(range(1, 10)), list(range(201, 210)))
    )

    graph.delete_outliers_button.click()

    callback.assert_called_once_with([209])
