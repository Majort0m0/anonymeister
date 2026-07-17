from __future__ import annotations

from typing import Callable

_DE_NAME_POOL = [
    "Anna Bergmann",
    "Max Hoffmann",
    "Laura Schneider",
    "Jonas Weber",
    "Sophie Wagner",
    "Lukas Becker",
    "Marie Schulz",
    "Felix Richter",
    "Hannah Klein",
    "Paul Wolf",
    "Lena Neumann",
    "Tim Schwarz",
    "Julia Zimmermann",
    "David Braun",
    "Sarah Krüger",
    "Simon Hofmann",
    "Nina Lange",
    "Jan Schmid",
    "Katharina Vogel",
    "Tobias Fischer",
    "Emma Werner",
    "Niklas Krause",
    "Clara Meyer",
    "Moritz Huber",
    "Johanna Kaiser",
    "Erik Fuchs",
    "Sophia Peters",
    "Leon Winkler",
    "Amelie Horn",
    "Fabian Graf",
    "Charlotte Busch",
    "Benjamin Sommer",
    "Marlene Keller",
    "Philipp Voss",
    "Isabel Kramer",
]

_EN_NAME_POOL = [
    "James Anderson",
    "Emily Carter",
    "Michael Brooks",
    "Olivia Bennett",
    "Daniel Foster",
    "Sophia Hayes",
    "William Turner",
    "Grace Mitchell",
    "Henry Parker",
    "Ava Morgan",
    "Benjamin Reed",
    "Charlotte Hughes",
    "Samuel Cooper",
    "Isabella Ward",
    "Joseph Bailey",
    "Amelia Russell",
    "Thomas Griffin",
    "Chloe Simmons",
    "Andrew Fleming",
    "Zoe Whitfield",
    "Christopher Doyle",
    "Hannah Sinclair",
    "Matthew Palmer",
    "Ella Sutton",
    "Nathan Brewer",
    "Lucy Sheppard",
    "Ryan Chambers",
    "Megan Ashford",
    "Jacob Everett",
    "Natalie Cross",
    "Ethan Marsh",
    "Victoria Lowe",
    "Owen Blackwood",
    "Rebecca Stone",
    "Adam Whitmore",
]


def make_person_pseudonymizer(language: str = "de") -> Callable[[str], str]:
    """Return a closure that maps distinct PERSON texts to consistent fake names.

    Every call with the same `original_text` on the returned function yields the
    same pseudonym for the lifetime of that function instance; each call to
    `make_person_pseudonymizer()` starts a brand-new, independent mapping.
    """
    pool = _DE_NAME_POOL if language == "de" else _EN_NAME_POOL
    assigned: dict[str, str] = {}

    def fn(original_text: str) -> str:
        if original_text not in assigned:
            assigned[original_text] = pool[len(assigned) % len(pool)]
        return assigned[original_text]

    return fn


def make_person_numberer() -> Callable[[str], str]:
    """Return a closure that maps distinct PERSON texts to consistent numbered
    placeholders ("[PERSON1]", "[PERSON2]", ...), assigned in first-seen order.

    Same per-call-instance consistency contract as make_person_pseudonymizer():
    it stays fully redacted (no real or fake name is exposed) while still
    letting a reader tell distinct people in the document apart. As with the
    pseudonymizer, the mapping key is the literal matched text, so different
    surface forms of the same person (full name vs. surname only) get
    different numbers — there is no cross-mention coreference resolution.
    """
    assigned: dict[str, str] = {}

    def fn(original_text: str) -> str:
        if original_text not in assigned:
            assigned[original_text] = f"[PERSON{len(assigned) + 1}]"
        return assigned[original_text]

    return fn
