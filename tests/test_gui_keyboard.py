"""Keyboard focus state stays aligned with button availability without starting Tk."""

from types import SimpleNamespace

import pytest

from thesislint import gui


@pytest.mark.parametrize("enabled", [False, True])
def test_button_enabled_state_and_tab_focus_stay_synchronized(enabled):
    app = gui.App.__new__(gui.App)
    options = {
        "state": "disabled" if enabled else "normal",
        "takefocus": not enabled,
    }
    button = SimpleNamespace(configure=options.update)

    app._set_enabled(button, enabled)

    assert options["state"] == ("normal" if enabled else "disabled")
    assert options["takefocus"] is enabled
