"""
Basic tests for an application.

This ensures all modules are importable and that the config is valid.
"""

def test_import_app():
    from schnieder_vsd.application import SchniederVsdApplication
    assert SchniederVsdApplication

def test_config():
    from schnieder_vsd.app_config import SchniederVsdConfig

    config = SchniederVsdConfig()
    assert isinstance(config.to_dict(), dict)

def test_ui():
    from schnieder_vsd.app_ui import SchniederVsdUI
    assert SchniederVsdUI

def test_state():
    from schnieder_vsd.app_state import SchniederVsdState
    assert SchniederVsdState