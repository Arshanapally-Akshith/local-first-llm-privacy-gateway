"""get_tier1_detectors() exposes exactly the registered Tier-1
detectors, in registration order, without a mutable list leaking
registry internals to callers."""

from src.detect.registry import get_tier1_detectors


def test_returns_one_detector_per_registered_entity_type() -> None:
    detectors = get_tier1_detectors()

    entity_types = [detector.entity_type for detector in detectors]
    assert entity_types == [
        "AADHAAR",
        "CARD",
        "PAN",
        "IFSC",
        "UPI",
        "VEHICLE_REG",
        "EMAIL",
        "PHONE",
    ]


def test_every_returned_detector_is_tier_one() -> None:
    detectors = get_tier1_detectors()

    assert all(detector.tier == 1 for detector in detectors)


def test_returned_sequence_is_not_a_plain_mutable_list() -> None:
    detectors = get_tier1_detectors()

    assert not isinstance(detectors, list)
