# SPDX-License-Identifier: Apache-2.0
"""Foreign word detection and Polish phonetic transcription (AI-02, AI-08, D-12).

Detects English and foreign tokens using orthographic signals and vendored English
word lists, proposing Polish spoken phonetic equivalents (e.g. Walker -> Łoker).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ForeignMatch:
    """A detected foreign token match in text."""

    start: int
    end: int
    original: str
    proposed: str
    category: str = "foreign_word"
    rationale: str = ""
    confidence: float = 0.85


# Specific curated phonetic mappings for high-frequency English terms and names
KNOWN_FOREIGN_PRONUNCIATIONS: dict[str, str] = {
    "walker": "Łoker",
    "deadline": "Dedlajn",
    "briefing": "Brifing",
    "software": "Softwer",
    "hardware": "Hardwer",
    "weekend": "Łikend",
    "feedback": "Fidbek",
    "manager": "Menedżer",
    "management": "Menedżment",
    "online": "Onlajn",
    "offline": "Oflajn",
    "open space": "Ołpen spejs",
    "meeting": "Miting",
    "call": "Kol",
    "standup": "Stendap",
    "sprint": "Sprint",
    "backlog": "Beklog",
    "workflow": "Łorkfloł",
    "leader": "Lider",
    "team": "Tim",
    "smith": "Smit",
    "johnson": "Dżonson",
    "williams": "Łilliams",
    "brown": "Brałn",
    "jones": "Dżołns",
    "miller": "Miler",
    "davis": "Dejwis",
    "wilson": "Łilson",
    "taylor": "Tejlor",
    "clark": "Klark",
    "white": "Łajt",
    "black": "Blek",
    "green": "Grin",
    "hall": "Hol",
    "young": "Jang",
    "king": "King",
    "wright": "Rajt",
    "scott": "Skot",
    "baker": "Bejker",
    "adams": "Adams",
    "nelson": "Nelson",
    "carter": "Karter",
    "mitchell": "Miczel",
    "roberts": "Roberts",
    "turner": "Terner",
    "phillips": "Filips",
    "campbell": "Kambel",
    "parker": "Parker",
    "evans": "Ewans",
    "edwards": "Edłards",
    "collins": "Kolins",
    "stewart": "Stiuart",
    "sanchez": "Sanczez",
    "morris": "Moris",
    "rogers": "Rodżers",
    "reed": "Rid",
    "cook": "Kuk",
    "morgan": "Morgan",
    "bell": "Bel",
    "murphy": "Merfi",
    "bailey": "Bejli",
    "rivera": "Riwiera",
    "cooper": "Kuper",
    "richardson": "Riczardson",
    "cox": "Koks",
    "howard": "Hałard",
    "ward": "Łord",
    "torres": "Torres",
    "peterson": "Piterson",
    "gray": "Grej",
    "ramirez": "Ramirez",
    "james": "Dżejms",
    "watson": "Łotson",
    "brooks": "Bruks",
    "kelly": "Keli",
    "sanders": "Sanders",
    "price": "Prajs",
    "bennett": "Benet",
    "wood": "Łud",
    "barnes": "Barns",
    "ross": "Ros",
    "henderson": "Henderson",
    "coleman": "Kolman",
    "jenkins": "Dżenkins",
    "perry": "Peri",
    "powell": "Pałel",
    "long": "Long",
    "patterson": "Paterson",
    "hughes": "Hjuz",
    "flores": "Flores",
    "washington": "Łoszynkton",
    "butler": "Batler",
    "simmons": "Simons",
    "foster": "Foster",
    "gonzales": "Gonzales",
    "bryant": "Brajant",
    "alexander": "Aleksander",
    "russell": "Rasel",
    "griffin": "Grifin",
    "diaz": "Diaz",
    "hayes": "Hejs",
}

# Polish diacritics - presence indicates Polish word, not English
POLISH_DIACRITICS = set("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ")

# English-specific orthographic signals (D-12)
ENGLISH_ORTHOGRAPHY_PATTERNS = [
    re.compile(r"th", re.I),
    re.compile(r"wh", re.I),
    re.compile(r"qu", re.I),
    re.compile(r"ck", re.I),
    re.compile(r"oo", re.I),
    re.compile(r"ee", re.I),
    re.compile(r"igh", re.I),
    re.compile(r"ough", re.I),
    re.compile(r"tion\b", re.I),
    re.compile(r"sion\b", re.I),
    re.compile(r"ness\b", re.I),
    re.compile(r"ment\b", re.I),
    re.compile(r"ing\b", re.I),
    re.compile(r"ght\b", re.I),
    re.compile(r"alk\b", re.I),
    re.compile(r"\bwr", re.I),
    re.compile(r"\bkn", re.I),
]

_ENGLISH_WORDS_CACHE: set[str] | None = None


def _load_english_words() -> set[str]:
    global _ENGLISH_WORDS_CACHE
    if _ENGLISH_WORDS_CACHE is None:
        path = Path(__file__).parent / "data" / "english_words.txt"
        if path.exists():
            with open(path, encoding="utf-8") as f:
                lines = [
                    line.strip().lower() for line in f if line.strip() and not line.startswith("#")
                ]
                _ENGLISH_WORDS_CACHE = set(lines)
        else:
            _ENGLISH_WORDS_CACHE = set()
    return _ENGLISH_WORDS_CACHE


def has_english_orthography(token: str) -> bool:
    """Check if token carries English-specific letter combinations."""
    return any(pat.search(token) for pat in ENGLISH_ORTHOGRAPHY_PATTERNS)


def approximate_polish_phonetics(word: str) -> str:
    """Provide a rule-based Polish phonetic approximation for an English word."""
    lower = word.lower()
    if lower in KNOWN_FOREIGN_PRONUNCIATIONS:
        # Match case of original first letter
        pron = KNOWN_FOREIGN_PRONUNCIATIONS[lower]
        return pron if word[0].isupper() else pron.lower()

    # Rule-based phonetics
    res = lower
    # W -> Ł
    res = re.sub(r"^w", "ł", res)
    res = re.sub(r"([aeiou])w", r"\1ł", res)
    # tion -> szyn
    res = re.sub(r"tion$", "szyn", res)
    res = re.sub(r"sion$", "żyn", res)
    # ee, ea -> i
    res = re.sub(r"ee", "i", res)
    res = re.sub(r"ea", "e", res)
    # oo -> u
    res = re.sub(r"oo", "u", res)
    # ck -> k
    res = re.sub(r"ck", "k", res)
    # th -> t
    res = re.sub(r"th", "t", res)
    # sh -> sz
    res = re.sub(r"sh", "sz", res)
    # ch -> cz
    res = re.sub(r"ch", "cz", res)
    # qu -> kł
    res = re.sub(r"qu", "kł", res)
    # x -> ks
    res = re.sub(r"x", "ks", res)

    if word[0].isupper():
        res = res.capitalize()
    return res


RE_WORD = re.compile(r"\b[A-Za-z]{3,20}\b")


def detect_foreign_words(
    text: str,
    user_lexicon_words: set[str] | None = None,
) -> list[ForeignMatch]:
    """Detect foreign (English) tokens in text using D-12 rules.

    A token is flagged if:
    1. It has NO Polish diacritics.
    2. It is not in user lexicon.
    3. It is in the English wordlist AND carries English orthographic signals, OR is a known foreign term.
    """
    matches: list[ForeignMatch] = []
    english_words = _load_english_words()
    user_lex = user_lexicon_words or set()

    for m in RE_WORD.finditer(text):
        token = m.group(0)
        lower = token.lower()

        # Check for Polish diacritics
        if any(c in POLISH_DIACRITICS for c in token):
            continue

        if lower in user_lex:
            continue

        is_known = lower in KNOWN_FOREIGN_PRONUNCIATIONS
        is_eng_ortho = (lower in english_words) and has_english_orthography(lower)

        if is_known or is_eng_ortho:
            spoken = approximate_polish_phonetics(token)
            matches.append(
                ForeignMatch(
                    start=m.start(),
                    end=m.end(),
                    original=token,
                    proposed=spoken,
                    category="foreign_word",
                    rationale=f"English token with phonetic rewrite: {token} -> {spoken}",
                    confidence=0.85,
                )
            )

    return matches
