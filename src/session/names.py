"""The production-sized candidate list for `PERSON` name-surrogate
allocation (Phase 4 Task 5), superseding Phase 3's 40-entry placeholder.

Generated, not hand-typed: a first-name pool and a last-name pool
(~70 entries each, all single tokens, pan-Indian in origin — no
compound names, so a cartesian join with a single space never produces
an ambiguous or colliding boundary) are combined into every "First
Last" pairing. This mirrors this project's own benchmark-generation
philosophy (BUILD.md: "slot carriers... entities injected
programmatically") applied to a candidate *pool* rather than a labeled
dataset — the alternative, typing ~5,000 individual names by hand, is
exactly the kind of manual-data time sink this project's methodology
exists to avoid elsewhere.

Sized to match ARCHITECTURE.md's own collision-math illustration
("a ~5,000-name list and ~60 distinct people in a session gives roughly
a 30% birthday-collision probability") — 72 first names x 71 last names
= 5,112 candidates, in the same order of magnitude as that number.
"""

from typing import Final

_FIRST_NAMES: Final[tuple[str, ...]] = (
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh", "Krishna",
    "Ishaan", "Rohan", "Kabir", "Advik", "Vivan", "Atharv", "Ayaan", "Yash",
    "Dhruv", "Karthik", "Rahul", "Siddharth", "Aryan", "Rudra", "Vedant", "Aarush",
    "Devansh", "Kian", "Rishi", "Arnav", "Shaurya", "Veer", "Aakash", "Aman",
    "Deepak", "Gaurav", "Harsh", "Manish", "Naveen", "Pankaj", "Raj", "Sanjay",
    "Sunil", "Tarun", "Uday", "Vikram", "Ananya", "Diya", "Saanvi", "Aadhya",
    "Kiara", "Myra", "Anika", "Navya", "Pari", "Riya", "Meera", "Priya",
    "Neha", "Pooja", "Kavya", "Tanvi", "Ishita", "Aisha", "Zara", "Fatima",
    "Divya", "Shreya", "Sneha", "Anjali", "Bhavna", "Charu", "Deepika", "Esha",
)
"""72 single-token first names, deliberately spanning multiple linguistic/
regional origins (Hindi, Tamil, Telugu, Punjabi, Urdu, Sanskrit-derived)
to match this project's stated Hinglish/pan-Indian scope — not a
synthetic dataset label, just a source pool for surrogate generation."""

_LAST_NAMES: Final[tuple[str, ...]] = (
    "Sharma", "Gupta", "Verma", "Reddy", "Nair", "Iyer", "Rao", "Menon",
    "Pillai", "Kapoor", "Joshi", "Patel", "Desai", "Shah", "Mehta", "Chaudhary",
    "Bose", "Chatterjee", "Mukherjee", "Banerjee", "Malhotra", "Sinha", "Chopra", "Bhatt",
    "Trivedi", "Choudhary", "Agarwal", "Subramaniam", "Krishnan", "Rajan", "Ramesh", "Venkatesh",
    "Krishnamurthy", "Balasubramaniam", "Narayanan", "Raghavan", "Sundaram", "Khan", "Sheikh",
    "Bhattacharya", "Ghosh", "Das", "Dutta", "Sengupta", "Iyengar", "Nambiar", "Warrier",
    "Kulkarni", "Deshmukh", "Bhosale", "Jadhav", "Pawar", "Gaikwad", "Naidu", "Chowdhury",
    "Roy", "Saxena", "Mathur", "Kaul", "Dhawan", "Bajaj", "Goyal", "Jain",
    "Bansal", "Aggarwal", "Arora", "Khanna", "Sethi", "Anand", "Kohli", "Bhalla",
)
"""71 single-token surnames, spanning the same regional breadth as
`_FIRST_NAMES` — no entry here is also a first name, so no cartesian
pairing can accidentally read as "Last First" instead of "First Last"."""


def _generate_name_candidates() -> tuple[str, ...]:
    return tuple(f"{first} {last}" for first in _FIRST_NAMES for last in _LAST_NAMES)


DEFAULT_NAME_CANDIDATES: Final[tuple[str, ...]] = _generate_name_candidates()
"""Every `_FIRST_NAMES` x `_LAST_NAMES` combination, as one flat,
deduplicated-by-construction tuple (two disjoint single-token pools
joined by a single space can never produce the same "First Last"
string from two different pairs)."""
