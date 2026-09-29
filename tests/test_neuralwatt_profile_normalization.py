"""Profile rows report the known NeuralWatt endpoint consistently."""

import api.profiles as profiles


def test_neuralwatt_endpoint_normalizes_a_custom_profile_provider():
    assert profiles.normalized_profile_provider(
        "custom", "https://api.neuralwatt.com/v1"
    ) == "neuralwatt"


def test_neuralwatt_endpoint_normalizes_legacy_named_custom_provider():
    """Profiles saved through an earlier custom-provider form retain quota support."""
    assert profiles.normalized_profile_provider(
        "custom:api-nw", "https://api.neuralwatt.com/v1"
    ) == "neuralwatt"


def test_unrelated_custom_endpoint_stays_custom():
    assert profiles.normalized_profile_provider(
        "custom", "https://proxy.example.test/v1"
    ) == "custom"
