"""benchmarks.arms.presidio_label_map: the shared Presidio-label ->
EntityType table itself — static validation independent of any
particular Presidio run, so a typo'd entry is caught here directly."""

from src.core.types import ENTITY_TYPES

from benchmarks.arms.presidio_label_map import PRESIDIO_LABEL_TO_ENTITY_TYPE


def test_every_mapped_value_is_a_known_entity_type() -> None:
    for entity_type in PRESIDIO_LABEL_TO_ENTITY_TYPE.values():
        assert entity_type in ENTITY_TYPES


def test_maps_the_four_types_presidio_already_attempts_out_of_the_box() -> None:
    assert PRESIDIO_LABEL_TO_ENTITY_TYPE == {
        "CREDIT_CARD": "CARD",
        "EMAIL_ADDRESS": "EMAIL",
        "PHONE_NUMBER": "PHONE",
        "PERSON": "PERSON",
    }


def test_the_five_custom_recognizer_types_are_deliberately_absent() -> None:
    # AADHAAR/PAN/IFSC/UPI/VEHICLE_REG are not stock Presidio labels at
    # all - our custom recognizers (recognizers.py) emit our own
    # EntityType strings directly, so they need no entry in this table.
    for entity_type in ("AADHAAR", "PAN", "IFSC", "UPI", "VEHICLE_REG"):
        assert entity_type not in PRESIDIO_LABEL_TO_ENTITY_TYPE
        assert entity_type not in PRESIDIO_LABEL_TO_ENTITY_TYPE.values()
