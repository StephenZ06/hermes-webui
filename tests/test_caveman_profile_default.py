from api import config


def test_profile_config_defaults_to_caveman_personality():
    data = {"agent": {"personalities": {"custom": "Custom."}}}

    config._apply_config_defaults(data)

    assert data["personality"] == "caveman"


def test_profile_config_caveman_default_overrides_other_profile_personality():
    data = {"personality": "helpful"}

    config._apply_config_defaults(data)

    assert data["personality"] == "caveman"
