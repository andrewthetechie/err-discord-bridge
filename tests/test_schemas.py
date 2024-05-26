from discord_bridge.schemas import BridgeConfig
import pytest

from pydantic import ValidationError


def test_bridge_config_check_for_config():
    data = {
        "OneWay": [],
        "TwoWay": [],
        "Reply": [],
    }

    with pytest.raises(ValidationError):
        BridgeConfig(**data)
    data = {
        "OneWay": [
            {
                "source": {"src": "err", "identifier": "@errbot"},
                "destination": {"dest": "discord", "identifier": "channeiid"},
            }
        ],
        "TwoWay": [
            {
                "source": {"src": "err", "identifier": "@errbot2way"},
                "destination": {"dest": "discord", "identifier": "2waychanneiid"},
            }
        ],
        "Reply": [],
    }
    bc = BridgeConfig(**data)
    assert len(bc.one_way) == 1
    assert len(bc.two_way) == 1


def test_bridge_destinations():
    """This test tests the destinations property of the BridgeConfig Schema"""
    data = {
        "OneWay": [
            {
                "source": {"src": "err", "identifier": "@errbot"},
                "destination": {"dest": "discord", "identifier": "channeiid"},
            }
        ],
        "TwoWay": [
            {
                "source": {"src": "err", "identifier": "@errbot2way"},
                "destination": {"dest": "discord", "identifier": "2waychanneiid"},
            }
        ],
    }
    bc = BridgeConfig(**data)
    assert len(bc.destinations.keys()) == 2
    # TODO: This test could use some improvement, test the destinations data a bit deeper
