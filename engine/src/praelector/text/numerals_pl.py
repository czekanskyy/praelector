# SPDX-License-Identifier: Apache-2.0
"""Polish numeral pronunciation generation and detection (D-11).

Provides cardinal, ordinal (m/f/n), year, decimal, time, and Roman numeral
conversions to phonetic spoken Polish text without third-party LGPL dependencies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Base cardinal components
ONES_CARDINAL = [
    "",
    "jeden",
    "dwa",
    "trzy",
    "cztery",
    "pięć",
    "sześć",
    "siedem",
    "osiem",
    "dziewięć",
]

TEENS_CARDINAL = [
    "dziesięć",
    "jedenaście",
    "dwanaście",
    "trzynaście",
    "czternaście",
    "piętnaście",
    "szesnaście",
    "siedemnaście",
    "osiemnaście",
    "dziewiętnaście",
]

TENS_CARDINAL = [
    "",
    "",
    "dwadzieścia",
    "trzydzieści",
    "czterdzieści",
    "pięćdziesiąt",
    "sześćdziesiąt",
    "siedemdziesiąt",
    "osiemdziesiąt",
    "dziewięćdziesiąt",
]

HUNDREDS_CARDINAL = [
    "",
    "sto",
    "dwieście",
    "trzysta",
    "czterysta",
    "pięćset",
    "sześćset",
    "siedemset",
    "osiemset",
    "dziewięćset",
]

# Ordinal components (m, f, n)
ONES_ORDINAL: dict[str, list[str]] = {
    "m": [
        "",
        "pierwszy",
        "drugi",
        "trzeci",
        "czwarty",
        "piąty",
        "szósty",
        "siódmy",
        "ósmy",
        "dziewiąty",
    ],
    "f": [
        "",
        "pierwsza",
        "druga",
        "trzecia",
        "czwarta",
        "piąta",
        "szósta",
        "siódma",
        "ósma",
        "dziewiąta",
    ],
    "n": [
        "",
        "pierwsze",
        "drugie",
        "trzecie",
        "czwarte",
        "piąte",
        "szóste",
        "siódme",
        "ósme",
        "dziewiąte",
    ],
}

TEENS_ORDINAL: dict[str, list[str]] = {
    "m": [
        "dziesiąty",
        "jedenasty",
        "dwunasty",
        "trzynasty",
        "czternasty",
        "piętnasty",
        "szesnasty",
        "siedemnasty",
        "osiemnasty",
        "dziewiętnasty",
    ],
    "f": [
        "dziesiąta",
        "jedenasta",
        "dwunasta",
        "trzynasta",
        "czternasta",
        "piętnasta",
        "szesnasta",
        "siedemnasta",
        "osiemnasta",
        "dziewiętnasta",
    ],
    "n": [
        "dziesiąte",
        "jedenaste",
        "dwunaste",
        "trzynaste",
        "czternaste",
        "piętnaste",
        "szesnaste",
        "siedemnaste",
        "osiemnaste",
        "dziewiętnaste",
    ],
}

TENS_ORDINAL: dict[str, list[str]] = {
    "m": [
        "",
        "",
        "dwudziesty",
        "trzydziesty",
        "czterdziesty",
        "pięćdziesiąty",
        "sześćdziesiąty",
        "siedemdziesiąty",
        "osiemdziesiąty",
        "dziewięćdziesiąty",
    ],
    "f": [
        "",
        "",
        "dwudziesta",
        "trzydziesta",
        "czterdziesta",
        "pięćdziesiąta",
        "sześćdziesiąta",
        "siedemdziesiąta",
        "osiemdziesiąta",
        "dziewięćdziesiąta",
    ],
    "n": [
        "",
        "",
        "dwudzieste",
        "trzydzieste",
        "czterdzieste",
        "pięćdziesiąte",
        "sześćdziesiąte",
        "siedemdziesiąte",
        "osiemdziesiąte",
        "dziewięćdziesiąte",
    ],
}

HUNDREDS_ORDINAL: dict[str, list[str]] = {
    "m": [
        "",
        "setny",
        "dwusetny",
        "trzystny",
        "czterechsetny",
        "pięćsetny",
        "sześćsetny",
        "siedemsetny",
        "osiemsetny",
        "dziewięćsetny",
    ],
    "f": [
        "",
        "setna",
        "dwusetna",
        "trzystna",
        "czterechsetna",
        "pięćsetna",
        "sześćsetna",
        "siedemsetna",
        "osiemsetna",
        "dziewięćsetna",
    ],
    "n": [
        "",
        "setne",
        "dwusetne",
        "trzystne",
        "czterechsetne",
        "pięćsetne",
        "sześćsetne",
        "siedemsetne",
        "osiemsetne",
        "dziewięćsetne",
    ],
}

ROMAN_VALS = [
    ("M", 1000),
    ("CM", 900),
    ("D", 500),
    ("CD", 400),
    ("C", 100),
    ("XC", 90),
    ("L", 50),
    ("XL", 40),
    ("X", 10),
    ("IX", 9),
    ("V", 5),
    ("IV", 4),
    ("I", 1),
]

NEUTER_NOUNS = {
    "piętro",
    "piętrze",
    "stulecie",
    "stuleciu",
    "wydanie",
    "wydaniu",
    "święto",
    "święcie",
    "pokolenie",
    "pokoleniu",
    "miejsce",
    "miejscu",
    "danie",
    "daniu",
    "zadanie",
    "zadaniu",
    "ćwiczenie",
    "ćwiczeniu",
}

FEMININE_NOUNS = {
    "klasa",
    "klasie",
    "część",
    "części",
    "edycja",
    "edycji",
    "godzina",
    "godzinie",
    "godziny",
    "strona",
    "stronie",
    "brama",
    "bramie",
    "aleja",
    "alei",
    "brygada",
    "brygadzie",
    "dywizja",
    "dywizji",
    "scena",
    "scenie",
    "księga",
    "księdze",
}

MASCULINE_NOUNS = {
    "wiek",
    "wieku",
    "wiekiem",
    "rozdział",
    "rozdziale",
    "rozdziału",
    "tom",
    "tomie",
    "tomu",
    "dzień",
    "dniu",
    "punkt",
    "punkcie",
    "punktu",
    "stopień",
    "stopniu",
    "rząd",
    "rzędzie",
    "rok",
    "roku",
    "miesiąc",
    "miesiącu",
    "akt",
    "akcie",
}


@dataclass(frozen=True)
class NumeralMatch:
    """A detected numeral match in text."""

    start: int
    end: int
    original: str
    proposed: str
    category: str
    rationale: str
    confidence: float


def _plural_form(n: int, singular: str, paucal: str, plural: str) -> str:
    """Pick proper Polish plural form for scale words."""
    if n == 1:
        return singular
    tens = (n // 10) % 10
    ones = n % 10
    if tens != 1 and 2 <= ones <= 4:
        return paucal
    return plural


def _convert_group_cardinal(n: int) -> list[str]:
    """Convert a 3-digit group (0..999) to cardinal words."""
    words: list[str] = []
    h = (n // 100) % 10
    t = (n // 10) % 10
    o = n % 10

    if h > 0:
        words.append(HUNDREDS_CARDINAL[h])

    if t == 1:
        words.append(TEENS_CARDINAL[o])
    else:
        if t > 1:
            words.append(TENS_CARDINAL[t])
        if o > 0:
            words.append(ONES_CARDINAL[o])

    return words


def cardinal_nominative(n: int) -> str:
    """Convert an integer to Polish cardinal nominative (e.g. 238 -> dwieście trzydzieści osiem)."""
    if n == 0:
        return "zero"
    if n < 0:
        return "minus " + cardinal_nominative(-n)

    parts: list[str] = []

    # Billions
    billions = (n // 1_000_000_000) % 1000
    if billions > 0:
        if billions == 1:
            parts.append("miliard")
        else:
            parts.extend(_convert_group_cardinal(billions))
            parts.append(_plural_form(billions, "miliard", "miliardy", "miliardów"))

    # Millions
    millions = (n // 1_000_000) % 1000
    if millions > 0:
        if millions == 1:
            parts.append("milion")
        else:
            parts.extend(_convert_group_cardinal(millions))
            parts.append(_plural_form(millions, "milion", "miliony", "milionów"))

    # Thousands
    thousands = (n // 1000) % 1000
    if thousands > 0:
        if thousands == 1:
            parts.append("tysiąc")
        else:
            parts.extend(_convert_group_cardinal(thousands))
            parts.append(_plural_form(thousands, "tysiąc", "tysiące", "tysięcy"))

    # Ones
    remainder = n % 1000
    if remainder > 0:
        parts.extend(_convert_group_cardinal(remainder))

    return " ".join(parts)


def ordinal_nominative(n: int, gender: str = "m") -> str:
    """Convert an integer 1..999999 to Polish ordinal nominative.

    gender: 'm' (męski), 'f' (żeński), 'n' (nijaki).
    In Polish, only the tens and units (or the last non-zero component) take ordinal form.
    """
    if n <= 0:
        return str(n)
    if gender not in ("m", "f", "n"):
        gender = "m"

    # Exact thousands (1000, 2000, etc.)
    if n % 1000 == 0:
        th = n // 1000
        suffix = "tysięczny" if gender == "m" else ("tysięczna" if gender == "f" else "tysięczne")
        if th == 1:
            return suffix
        if th == 2:
            return f"dwu{suffix}"
        if th == 3:
            return f"trzy{suffix}"
        if th == 4:
            return f"cztero{suffix}"
        if th == 5:
            return f"pięcio{suffix}"
        return f"{cardinal_nominative(th)} {suffix}"

    parts: list[str] = []

    # Handle thousands as cardinals when remainder is non-zero
    thousands = n // 1000
    remainder = n % 1000

    if thousands > 0:
        if thousands == 1:
            parts.append("tysiąc")
        else:
            parts.append(cardinal_nominative(thousands))
            parts.append(_plural_form(thousands, "tysiąc", "tysiące", "tysięcy"))

    # Handle remainder (1..999)
    h = (remainder // 100) % 10
    t = (remainder // 10) % 10
    o = remainder % 10

    if t == 0 and o == 0 and h > 0:
        # e.g. 100, 200, 300
        parts.append(HUNDREDS_ORDINAL[gender][h])
        return " ".join(parts)

    if h > 0:
        parts.append(HUNDREDS_CARDINAL[h])

    if t == 1:
        parts.append(TEENS_ORDINAL[gender][o])
    elif t > 1 and o == 0:
        parts.append(TENS_ORDINAL[gender][t])
    elif t > 1 and o > 0:
        parts.append(TENS_ORDINAL[gender][t])
        parts.append(ONES_ORDINAL[gender][o])
    elif o > 0:
        parts.append(ONES_ORDINAL[gender][o])

    return " ".join(parts)


def year_to_words(year: int) -> str:
    """Convert a year (e.g. 1939) to Polish spoken format: tysiąc dziewięćset trzydziesty dziewiąty."""
    if year == 2000:
        return "dwutysięczny"
    return ordinal_nominative(year, gender="m")


def time_to_words(hours: int, minutes: int, has_preposition: bool = False) -> str:
    """Convert clock time (e.g. 18:00) to Polish.

    If has_preposition (e.g. 'o 18:00'):
      18:00 -> 'osiemnastej'
      18:30 -> 'osiemnastej trzydzieści'
    Else:
      18:00 -> 'osiemnasta'
      18:30 -> 'osiemnasta trzydzieści'
    """
    locative_fem = [
        "",
        "pierwszej",
        "drugiej",
        "trzeciej",
        "czwartej",
        "piątej",
        "szóstej",
        "siódmej",
        "ósmej",
        "dziewiątej",
        "dziesiątej",
        "jedenastej",
        "dwunastej",
        "trzynastej",
        "czternastej",
        "piętnastej",
        "szesnastej",
        "siedemnastej",
        "osiemnastej",
        "dziewiętnastej",
        "dwudziestej",
        "dwudziestej pierwszej",
        "dwudziestej drugiej",
        "dwudziestej trzeciej",
        "północy",
    ]

    nom_fem = [
        "północ",
        "pierwsza",
        "druga",
        "trzecia",
        "czwarta",
        "piąta",
        "szósta",
        "siódma",
        "ósma",
        "dziewiąta",
        "dziesiąta",
        "jedenasta",
        "dwunasta",
        "trzynasta",
        "czternasta",
        "piętnasta",
        "szesnasta",
        "siedemnasta",
        "osiemnasta",
        "dziewiętnasta",
        "dwudziesta",
        "dwudziesta pierwsza",
        "dwudziesta druga",
        "dwudziesta trzecia",
        "północ",
    ]

    if not (0 <= hours <= 24 and 0 <= minutes <= 59):
        return f"{hours}:{minutes:02d}"

    hour_word = locative_fem[hours] if has_preposition else nom_fem[hours]

    if minutes == 0:
        return hour_word

    min_word = cardinal_nominative(minutes)
    return f"{hour_word} {min_word}"


def decimal_to_words(val_str: str) -> str:
    """Convert decimal number (e.g. '3,5' or '3.5') to Polish readout."""
    sep = "," if "," in val_str else "."
    int_part_str, frac_part_str = val_str.split(sep, 1)

    try:
        int_val = int(int_part_str)
        frac_val = int(frac_part_str)
    except ValueError:
        return val_str

    int_words = cardinal_nominative(int_val)
    frac_len = len(frac_part_str)

    if frac_len == 1:
        frac_words = cardinal_nominative(frac_val)
        scale_word = _plural_form(frac_val, "dziesiąta", "dziesiąte", "dziesiątych")
        if frac_val == 1:
            frac_words = "jedna"
    elif frac_len == 2:
        frac_words = cardinal_nominative(frac_val)
        scale_word = _plural_form(frac_val, "setna", "setne", "setnych")
        if frac_val == 1:
            frac_words = "jedna"
    elif frac_len == 3:
        frac_words = cardinal_nominative(frac_val)
        scale_word = _plural_form(frac_val, "tysięczna", "tysięczne", "tysięcznych")
        if frac_val == 1:
            frac_words = "jedna"
    else:
        frac_words = cardinal_nominative(frac_val)
        scale_word = ""

    if scale_word:
        return f"{int_words} i {frac_words} {scale_word}"
    return f"{int_words} przecinek {frac_words}"


def roman_to_int(roman: str) -> int | None:
    """Convert Roman numeral string to integer (1..3999), or None if invalid."""
    roman = roman.strip().upper()
    if not roman or not re.fullmatch(
        r"^M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$", roman
    ):
        return None

    total = 0
    idx = 0
    for roman_str, val in ROMAN_VALS:
        while roman.startswith(roman_str, idx):
            total += val
            idx += len(roman_str)
    return total if idx == len(roman) and total > 0 else None


def roman_to_words(roman: str, following_word: str | None = None) -> str:
    """Convert Roman numeral to ordinal Polish form respecting context gender."""
    val = roman_to_int(roman)
    if val is None:
        return roman

    gender = "m"
    if following_word:
        w = following_word.lower().strip(".,!?:;\"'()")
        if w in NEUTER_NOUNS:
            gender = "n"
        elif w in FEMININE_NOUNS:
            gender = "f"
        elif w in MASCULINE_NOUNS:
            gender = "m"
        else:
            # Fallback heuristic: words ending in 'o' or 'e' are often neuter
            if w.endswith(("o", "e")) and not w.endswith(("ie", "nie")):
                gender = "n"

    return ordinal_nominative(val, gender=gender)


# Regular expressions for detection
RE_ORDINAL_HEADING = re.compile(
    r"\b(Rozdział|Tom|Księga|Część|Akt|Scena)\s+([0-9]+|[IVXLCDM]+)\b",
    re.IGNORECASE,
)
RE_TIME = re.compile(
    r"(?:\b(o|około|przed|po)\s+)?\b([01]?[0-9]|2[0-3]):([0-5][0-9])\b", re.IGNORECASE
)
RE_DECIMAL = re.compile(r"\b(\d+)[,\.](\d+)\b")
RE_ROMAN = re.compile(r"\b([IVXLCDM]{1,8})\b")
RE_CARDINAL = re.compile(r"\b(\d{1,12})\b")


def detect_numerals(text: str) -> list[NumeralMatch]:
    """Detect all numeral constructs in a text block, generating Polish spoken suggestions."""
    matches: list[NumeralMatch] = []
    occupied_spans: list[tuple[int, int]] = []

    def _overlaps(s: int, e: int) -> bool:
        return any(max(s, os) < min(e, oe) for os, oe in occupied_spans)

    # 1. Heading ordinals (Rozdział 8, Tom I)
    for m in RE_ORDINAL_HEADING.finditer(text):
        label = m.group(1)
        num_str = m.group(2)
        gender = "m"
        lower_label = label.lower()
        if lower_label in ("część", "księga", "scena"):
            gender = "f"

        val: int | None = int(num_str) if num_str.isdigit() else roman_to_int(num_str)

        if val is not None and val > 0:
            ord_word = ordinal_nominative(val, gender=gender)
            prop = f"{label} {ord_word}"
            matches.append(
                NumeralMatch(
                    start=m.start(),
                    end=m.end(),
                    original=m.group(0),
                    proposed=prop,
                    category="ordinal_heading",
                    rationale=f"Ordinal heading in {gender} gender",
                    confidence=0.95,
                )
            )
            occupied_spans.append((m.start(), m.end()))

    # 2. Clock times (18:00, o 18:00)
    for m in RE_TIME.finditer(text):
        has_prep = bool(m.group(1))
        # Note: if there's a preposition, we target the digits span
        h = int(m.group(2))
        minute = int(m.group(3))
        time_start = m.start(2)
        time_end = m.end(3)

        if not _overlaps(time_start, time_end):
            spoken_time = time_to_words(h, minute, has_preposition=has_prep)
            matches.append(
                NumeralMatch(
                    start=time_start,
                    end=time_end,
                    original=text[time_start:time_end],
                    proposed=spoken_time,
                    category="numeral",
                    rationale=f"Clock time with {'locative' if has_prep else 'nominative'} readout",
                    confidence=0.95,
                )
            )
            occupied_spans.append((time_start, time_end))

    # 3. Decimals (3,5)
    for m in RE_DECIMAL.finditer(text):
        if not _overlaps(m.start(), m.end()):
            dec_spoken = decimal_to_words(m.group(0))
            matches.append(
                NumeralMatch(
                    start=m.start(),
                    end=m.end(),
                    original=m.group(0),
                    proposed=dec_spoken,
                    category="numeral",
                    rationale="Decimal number with Polish fraction suffix",
                    confidence=0.95,
                )
            )
            occupied_spans.append((m.start(), m.end()))

    # 4. Roman numerals (XIV piętro)
    for m in RE_ROMAN.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        token = m.group(1)
        val = roman_to_int(token)
        # Avoid false positives like single letters 'I' or 'V' unless capitalized Roman in context
        if val is None:
            continue
        # Look at the next word in the text
        rest = text[m.end() :].lstrip()
        next_word_match = re.match(r"^([A-Za-zżźćńółęąśŻŹĆĄŚĘŁÓŃ]+)", rest)
        next_word = next_word_match.group(1) if next_word_match else None

        spoken = roman_to_words(token, following_word=next_word)
        matches.append(
            NumeralMatch(
                start=m.start(),
                end=m.end(),
                original=token,
                proposed=spoken,
                category="numeral",
                rationale=f"Roman numeral {token} -> {spoken}",
                confidence=0.90,
            )
        )
        occupied_spans.append((m.start(), m.end()))

    # 5. Standalone cardinal integers / years (238, 1939)
    for m in RE_CARDINAL.finditer(text):
        if _overlaps(m.start(), m.end()):
            continue
        num = int(m.group(1))

        # Check if year pattern (1000..2099 preceded by 'w roku', 'roku', 'r.')
        preceding = text[: m.start()].rstrip().lower()
        is_year = (1000 <= num <= 2099) and (
            preceding.endswith(("roku", "w roku", "r."))
            or preceding.endswith(("latach", "od", "do"))
        )

        if is_year:
            spoken = year_to_words(num)
            rationale = "Year numeral"
        else:
            spoken = cardinal_nominative(num)
            rationale = "Cardinal integer"

        matches.append(
            NumeralMatch(
                start=m.start(),
                end=m.end(),
                original=m.group(1),
                proposed=spoken,
                category="numeral",
                rationale=rationale,
                confidence=0.95,
            )
        )
        occupied_spans.append((m.start(), m.end()))

    # Sort matches by start position
    matches.sort(key=lambda x: x.start)
    return matches
