"""Tests for tray icon menu behavior."""

import sys
from pathlib import Path
from unittest.mock import Mock

import pytest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, ".")

from ui.tray_icon import TrayIcon


@pytest.fixture(scope="module")
def app():
    """Provide a QApplication instance for tray icon tests."""
    instance = QApplication.instance()
    if instance is None:
        instance = QApplication([])
    return instance


def create_tray_icon(stats_panel=None) -> TrayIcon:
    """Create a tray icon with mocked stats panel methods."""
    if stats_panel is None:
        stats_panel = Mock()
    return TrayIcon(
        stats_panel=stats_panel,
        icon_path=Path("icons/icon.svg"),
        icon_paused_path=Path("icons/icon.svg"),
        icon_stopping_path=Path("icons/icon.svg"),
    )


class TestTrayIcon:
    """Test suite for tray icon menu updates."""

    def test_set_ollama_available_reuses_context_menu(self, app):
        """Repeated availability updates should reuse the same context menu."""
        tray_icon = create_tray_icon()
        original_menu = tray_icon.contextMenu()

        tray_icon.set_ollama_available(True)
        assert tray_icon.contextMenu() is original_menu

        tray_icon.set_ollama_available(False)
        assert tray_icon.contextMenu() is original_menu

    def test_ai_action_visibility_tracks_ollama_state(self, app):
        """AI action should be shown or hidden without rebuilding menu objects."""
        tray_icon = create_tray_icon()

        assert not tray_icon.practice_ai_action.isVisible()

        tray_icon.set_ollama_available(True)
        assert tray_icon.practice_ai_action.isVisible()

        tray_icon.set_ollama_available(False)
        assert not tray_icon.practice_ai_action.isVisible()

    def test_show_stats_emits_request_without_panel(self, app):
        """Tray stats action should work before the stats panel is created."""
        tray_icon = create_tray_icon(stats_panel=None)
        handler = Mock()
        tray_icon.stats_requested.connect(handler)

        tray_icon.show_stats()

        handler.assert_called_once_with()
