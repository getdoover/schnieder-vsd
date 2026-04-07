"""Basic tests for the Schneider VSD application."""


def test_app_class():
    from schneider_vsd.application import SchneiderVsdApplication

    assert SchneiderVsdApplication.config_cls is not None
    assert SchneiderVsdApplication.tags_cls is not None
    assert SchneiderVsdApplication.ui_cls is not None


def test_config_schema():
    from schneider_vsd.app_config import SchneiderVsdConfig

    schema = SchneiderVsdConfig.to_schema()
    assert isinstance(schema, dict)


def test_tags():
    from schneider_vsd.app_tags import SchneiderVsdTags

    assert SchneiderVsdTags is not None


def test_ui():
    from schneider_vsd.app_ui import SchneiderVsdUI

    assert SchneiderVsdUI is not None


def test_vsd_registry():
    from schneider_vsd.vsd import get_vsd_class
    from schneider_vsd.vsd.atv600 import ATV600

    assert get_vsd_class("atv600") is ATV600


def test_modbus_client():
    from schneider_vsd.modbus_client import ModbusTcpConnection

    conn = ModbusTcpConnection("127.0.0.1", 502, 1)
    assert conn.host == "127.0.0.1"
    assert conn.slave_id == 1
