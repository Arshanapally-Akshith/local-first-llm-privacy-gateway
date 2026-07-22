"""The slot-and-inject engine: fills one `CarrierTemplate`'s slots with
generated values and returns a `BenchmarkExample` whose gold spans are
exact by construction.

"Exact by construction" means what it says: this module never derives
an entity's offset by searching for its value inside the finished text
(`str.find`/regex search would be unsafe the moment a generated value,
or a substring of it, happens to also appear elsewhere in the carrier
sentence — e.g. the literal word "PAN" preceding a `{PAN}` slot). It
instead walks the template left to right, appending literal text and
generated values to a running buffer while tracking the cursor
position directly, so each gold span's `(start, end)` is read off the
cursor at the moment the value was appended — there is no separate
labelling step that could disagree with what was actually written.
"""

import random
import re
from typing import Final, cast

from src.core.types import ENTITY_TYPES, EntityType, Offset

from benchmarks.generate.dataset_types import BenchmarkExample, GoldEntity
from benchmarks.generate.entity_values import generate_value
from benchmarks.generate.templates import CarrierTemplate

_SLOT_PATTERN: Final[re.Pattern[str]] = re.compile(r"\{([A-Z_]+)\}")
"""Matches a `{TYPE}` slot token. The capturing group is what makes
`re.split` below hand back the slot names themselves, interleaved with
the literal text segments around them."""


def fill_template(
    template: CarrierTemplate, rng: random.Random, example_id: str
) -> BenchmarkExample:
    """Fill every slot in `template` with a freshly-generated value,
    using `rng`, and return the resulting example.

    Raises:
        ValueError: `template.text` references a slot name that is not
            a member of `src.core.types.ENTITY_TYPES` — a template
            authoring mistake (e.g. a typo), caught here rather than
            silently left as literal `{...}` text with no gold span.
    """
    segments = _SLOT_PATTERN.split(template.text)
    # re.split with one capturing group returns alternating
    # [literal, slot, literal, slot, ..., literal] — odd indices are
    # always slot names, even indices are always literal text,
    # regardless of how many slots the template contains.
    text_parts: list[str] = []
    entities: list[GoldEntity] = []
    cursor = 0
    for index, segment in enumerate(segments):
        if index % 2 == 0:
            text_parts.append(segment)
            cursor += len(segment)
            continue
        if segment not in ENTITY_TYPES:
            raise ValueError(
                f"template {template.template_id!r} references unknown slot "
                f"{{{segment}}} — not a member of ENTITY_TYPES"
            )
        entity_type = cast(EntityType, segment)  # membership already checked above
        value = generate_value(entity_type, rng)
        start = Offset(cursor)
        end = Offset(cursor + len(value))
        entities.append(GoldEntity(start=start, end=end, entity_type=entity_type, value=value))
        text_parts.append(value)
        cursor = end

    return BenchmarkExample(
        example_id=example_id,
        template_id=template.template_id,
        language=template.language,
        text="".join(text_parts),
        entities=tuple(entities),
    )
