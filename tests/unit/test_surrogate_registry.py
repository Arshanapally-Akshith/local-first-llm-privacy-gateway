"""get_surrogate_domain: returns the registered domain for each of the
six FF1-eligible types, and raises loudly (never a silent no-op) for
UPI/email — deferred to Phase 3's map — and for Tier-2 types."""

import pytest

from src.core.exceptions import SurrogateDomainError
from src.surrogate.registry import get_surrogate_domain


@pytest.mark.parametrize(
    "entity_type",
    ["AADHAAR", "PAN", "CARD", "IFSC", "PHONE", "VEHICLE_REG"],
)
def test_returns_a_domain_for_every_ff1_eligible_type(entity_type: str) -> None:
    domain = get_surrogate_domain(entity_type)  # type: ignore[arg-type]

    assert domain.entity_type == entity_type


@pytest.mark.parametrize("entity_type", ["UPI", "EMAIL", "PERSON", "ORG", "ADDRESS"])
def test_raises_for_types_with_no_registered_domain(entity_type: str) -> None:
    with pytest.raises(SurrogateDomainError, match="no surrogate domain registered"):
        get_surrogate_domain(entity_type)  # type: ignore[arg-type]
