"""The set of active surrogate domains, looked up by entity type.

Mirrors `src/detect/registry.py`'s explicit-registration shape, with
one difference: detectors are all *run* (a `Sequence`, iterated in
full every call); domains are *looked up by type* once a span's
`entity_type` is already known, so this is a `Mapping`.

UPI and email have no registered domain yet — both need the
session-scoped map Phase 3 introduces (see `docs/DECISIONS.md`), not
FF1. Looking either up here is a `SurrogateDomainError`, not a silent
no-op: an unsanitized UPI ID or email reaching the network is exactly
the leak this system exists to prevent, and a caller must find out
loudly, not by the value quietly failing to be replaced.
"""

from typing import Final

from src.core.exceptions import SurrogateDomainError
from src.core.types import EntityType
from src.surrogate.domain import SurrogateDomain
from src.surrogate.domains.aadhaar import AadhaarDomain
from src.surrogate.domains.card import CardDomain
from src.surrogate.domains.ifsc import IfscDomain
from src.surrogate.domains.pan import PanDomain
from src.surrogate.domains.phone import PhoneDomain
from src.surrogate.domains.vehicle_registration import VehicleRegistrationDomain

_DOMAINS: Final[dict[EntityType, SurrogateDomain]] = {
    domain.entity_type: domain
    for domain in (
        AadhaarDomain(),
        PanDomain(),
        CardDomain(),
        IfscDomain(),
        PhoneDomain(),
        VehicleRegistrationDomain(),
    )
}


def get_surrogate_domain(entity_type: EntityType) -> SurrogateDomain:
    """Return the registered `SurrogateDomain` for `entity_type`.

    Raises:
        SurrogateDomainError: no domain is registered for
            `entity_type` — currently true for `UPI`, `EMAIL`, and the
            Tier-2 types (`PERSON`, `ORG`, `ADDRESS`, which use the
            Phase 3 name map, never FF1).
    """
    domain = _DOMAINS.get(entity_type)
    if domain is None:
        raise SurrogateDomainError(f"no surrogate domain registered for entity_type={entity_type}")
    return domain
