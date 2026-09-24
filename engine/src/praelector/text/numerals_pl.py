# SPDX-License-Identifier: Apache-2.0
"""Polish cardinals, ordinals, years, decimals, clock times, and Roman numerals.

D-11: own module, not ``num2words``. Readings are nominative. A clock hour uses
the feminine locative (the form after „o”): ``18:00`` → ``osiemnastej``,
``14:30`` → ``czternastej trzydzieści``. A comma decimal reads
``3,5`` → ``trzy i pięć dziesiątych``. A bare year in 1000-2099 is the
masculine ordinal (``1989`` → ``tysiąc dziewięćset osiemdziesiąty dziewiąty``)
unless the next word is a quantity. The block text is not rewritten.
"""

from __future__ import annotations

import re
from typing import Literal

from praelector.domain.enums import SuggestionCategory
from praelector.text.suggestion import Suggestion, make_suggestion

Gender = Literal["m", "f", "n"]

_MAX_CARDINAL = 10**12 - 1

_UNITS = (
    "zero",
    "jeden",
    "dwa",
    "trzy",
    "cztery",
    "pięć",
    "sześć",
    "siedem",
    "osiem",
    "dziewięć",
)
_TEENS = (
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
)
_TENS = (
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
)
_HUNDREDS = (
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
)

# (masculine, feminine, neuter) nominative. 0 is only reached for a literal 0.
_ORD_LT20: tuple[tuple[str, str, str], ...] = (
    ("zerowy", "zerowa", "zerowe"),
    ("pierwszy", "pierwsza", "pierwsze"),
    ("drugi", "druga", "drugie"),
    ("trzeci", "trzecia", "trzecie"),
    ("czwarty", "czwarta", "czwarte"),
    ("piąty", "piąta", "piąte"),
    ("szósty", "szósta", "szóste"),
    ("siódmy", "siódma", "siódme"),
    ("ósmy", "ósma", "ósme"),
    ("dziewiąty", "dziewiąta", "dziewiąte"),
    ("dziesiąty", "dziesiąta", "dziesiąte"),
    ("jedenasty", "jedenasta", "jedenaste"),
    ("dwunasty", "dwunasta", "dwunaste"),
    ("trzynasty", "trzynasta", "trzynaste"),
    ("czternasty", "czternasta", "czternaste"),
    ("piętnasty", "piętnasta", "piętnaste"),
    ("szesnasty", "szesnasta", "szesnaste"),
    ("siedemnasty", "siedemnasta", "siedemnaste"),
    ("osiemnasty", "osiemnasta", "osiemnaste"),
    ("dziewiętnasty", "dziewiętnasta", "dziewiętnaste"),
)
_ORD_TENS: tuple[tuple[str, str, str], ...] = (
    ("", "", ""),
    ("", "", ""),
    ("dwudziesty", "dwudziesta", "dwudzieste"),
    ("trzydziesty", "trzydziesta", "trzydzieste"),
    ("czterdziesty", "czterdziesta", "czterdzieste"),
    ("pięćdziesiąty", "pięćdziesiąta", "pięćdziesiąte"),
    ("sześćdziesiąty", "sześćdziesiąta", "sześćdziesiąte"),
    ("siedemdziesiąty", "siedemdziesiąta", "siedemdziesiąte"),
    ("osiemdziesiąty", "osiemdziesiąta", "osiemdziesiąte"),
    ("dziewięćdziesiąty", "dziewięćdziesiąta", "dziewięćdziesiąte"),
)
_ORD_HUNDREDS: tuple[tuple[str, str, str], ...] = (
    ("", "", ""),
    ("setny", "setna", "setne"),
    ("dwusetny", "dwusetna", "dwusetne"),
    ("trzechsetny", "trzechsetna", "trzechsetne"),
    ("czterechsetny", "czterechsetna", "czterechsetne"),
    ("pięćsetny", "pięćsetna", "pięćsetne"),
    ("sześćsetny", "sześćsetna", "sześćsetne"),
    ("siedemsetny", "siedemsetna", "siedemsetne"),
    ("osiemsetny", "osiemsetna", "osiemsetne"),
    ("dziewięćsetny", "dziewięćsetna", "dziewięćsetne"),
)

# Stems used only when an exact multiple of a thousand takes ``-tysięczny``.
_UNIT_STEM = (
    "",
    "jedno",
    "dwu",
    "trzy",
    "cztero",
    "pięcio",
    "sześcio",
    "siedmio",
    "ośmio",
    "dziewięcio",
)
_TEEN_STEM = {
    10: "dziesięcio",
    11: "jedenasto",
    12: "dwunasto",
    13: "trzynasto",
    14: "czternasto",
    15: "piętnasto",
    16: "szesnasto",
    17: "siedemnasto",
    18: "osiemnasto",
    19: "dziewiętnasto",
}
_TENS_STEM = {
    2: "dwudziesto",
    3: "trzydziesto",
    4: "czterdziesto",
    5: "pięćdziesięcio",
    6: "sześćdziesięcio",
    7: "siedemdziesięcio",
    8: "osiemdziesięcio",
    9: "dziewięćdziesięcio",
}
_HUNDRED_STEM = {
    1: "stu",
    2: "dwustu",
    3: "trzystu",
    4: "czterystu",
    5: "pięćset",
    6: "sześćset",
    7: "siedemset",
    8: "osiemset",
    9: "dziewięćset",
}

_FRACTION = {
    1: ("dziesiąta", "dziesiąte", "dziesiątych"),
    2: ("setna", "setne", "setnych"),
    3: ("tysięczna", "tysięczne", "tysięcznych"),
}

# Nominative heading words. Inflected forms stay in ``_NOUN_GENDER`` so a
# locative noun still selects gender without being rewritten as a heading.
_HEADING_WORDS: dict[str, Gender] = {
    "rozdział": "m",
    "rozdzial": "m",
    "tom": "m",
    "akt": "m",
    "wiek": "m",
    "punkt": "m",
    "wstęp": "m",
    "wstep": "m",
    "chapter": "m",
    "część": "f",
    "czesc": "f",
    "księga": "f",
    "ksiega": "f",
    "scena": "f",
    "klasa": "f",
    "grupa": "f",
}

_NOUN_GENDER: dict[str, Gender] = {
    **_HEADING_WORDS,
    "rozdziału": "m",
    "rozdziale": "m",
    "rozdziałem": "m",
    "tomu": "m",
    "tomie": "m",
    "wieku": "m",
    "punktu": "m",
    "punkcie": "m",
    "wstępu": "m",
    "wstępie": "m",
    "części": "f",
    "czesci": "f",
    "księgi": "f",
    "ksiegi": "f",
    "księdze": "f",
    "księgę": "f",
    "sceny": "f",
    "scenie": "f",
    "scenę": "f",
    "klasy": "f",
    "klasie": "f",
    "grupy": "f",
    "grupie": "f",
    "godzina": "f",
    "godziny": "f",
    "godzinie": "f",
    "godzinę": "f",
    "sekcja": "f",
    "sekcji": "f",
    "piętro": "n",
    "pietro": "n",
    "piętra": "n",
    "pietra": "n",
    "piętrze": "n",
    "pietrze": "n",
    "piętrem": "n",
    "piętr": "n",
}

# A year followed by one of these is a quantity, not a calendar year.
_QUANTITIES = frozenset(
    {
        "zł",
        "zl",
        "pln",
        "km",
        "cm",
        "mm",
        "kg",
        "szt",
        "osób",
        "osoby",
        "razy",
        "procent",
        "metrów",
        "metr",
        "m",
        "stron",
        "strony",
        "egzemplarzy",
        "egzemplarze",
        "dolarów",
        "euro",
        "lat",
        "lata",
        "dni",
        "godzin",
    }
)

_ROMAN_VALUE = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_SUBTRACTIVE = {"IV": 4, "IX": 9, "XL": 40, "XC": 90, "CD": 400, "CM": 900}
_ROMAN_FORMAT = (
    (1000, "M"),
    (900, "CM"),
    (500, "D"),
    (400, "CD"),
    (100, "C"),
    (90, "XC"),
    (50, "L"),
    (40, "XL"),
    (10, "X"),
    (9, "IX"),
    (5, "V"),
    (4, "IV"),
    (1, "I"),
)

_GENDER_INDEX = {"m": 0, "f": 1, "n": 2}

_HEADING_RE = re.compile(
    r"(?i)(?<!\w)("
    + "|".join(re.escape(word) for word in sorted(_HEADING_WORDS, key=len, reverse=True))
    + r")[ \t]+(\d{1,4}|[IVXLCDM]{1,12})(?!\w)"
)
_CLOCK_RE = re.compile(r"(?<!\w)(\d{1,2}):(\d{2})(?![:\w])")
_DECIMAL_RE = re.compile(r"(?<!\w)(\d+),(\d+)(?!\w)")
_ROMAN_RE = re.compile(r"(?<!\w)([IVXLCDM]{1,15})(?!\w)")
_DOTTED_RE = re.compile(r"(?<!\w)(\d{1,6})\.(?!\d)")
_INTEGER_RE = re.compile(r"(?<!\w)(\d{1,3}(?:[ \u00a0]\d{3})+|\d{1,12})(?!\w)")
_NEXT_WORD = re.compile(r"""[\s.:;,_„«"'“(\-""" + "\u2014\u2013" + r"""]*([^\W\d_]+)""")
_PREV_WORD = re.compile(r"""([^\W\d_]+)[\s.:;,_»"'”)\)\-""" + "\u2014\u2013" + r"""]*$""")

_NUMERAL = SuggestionCategory.NUMERAL
_HEADING = SuggestionCategory.ORDINAL_HEADING


def cardinal(number: int) -> str:
    """Non-virile nominative cardinal. ``238`` → ``dwieście trzydzieści osiem``."""
    if number < 0 or number > _MAX_CARDINAL:
        raise ValueError("cardinal out of range")
    if number < 10:
        return _UNITS[number]
    if number < 20:
        return _TEENS[number - 10]
    if number < 100:
        tens, rest = divmod(number, 10)
        return _TENS[tens] if rest == 0 else f"{_TENS[tens]} {_UNITS[rest]}"
    if number < 1000:
        hundreds, rest = divmod(number, 100)
        head = _HUNDREDS[hundreds]
        return head if rest == 0 else f"{head} {cardinal(rest)}"
    if number < 1_000_000:
        return _scaled(number, 1000, "tysiąc", "tysiące", "tysięcy")
    if number < 1_000_000_000:
        return _scaled(number, 1_000_000, "milion", "miliony", "milionów")
    return _scaled(number, 1_000_000_000, "miliard", "miliardy", "miliardów")


def cardinal_feminine(number: int) -> str:
    """Cardinal with feminine ``jeden``/``dwa`` (fraction numerators)."""
    if number < 0:
        raise ValueError("cardinal out of range")
    spoken = cardinal(number)
    if number % 10 == 1 and number % 100 != 11 and spoken.endswith("jeden"):
        return "jedna" if spoken == "jeden" else spoken[:-5] + "jedna"
    if number % 10 == 2 and number % 100 != 12 and (spoken == "dwa" or spoken.endswith(" dwa")):
        return "dwie" if spoken == "dwa" else spoken[:-3] + "dwie"
    return spoken


def ordinal(number: int, gender: Gender = "m") -> str:
    """Nominative ordinal. Only the last non-zero component inflects.

    ``1939`` masculine is ``tysiąc dziewięćset trzydziesty dziewiąty``:
    the thousands and hundreds stay cardinal.
    """
    if number < 0 or number > 999_999:
        raise ValueError("ordinal out of range")
    if number < 20:
        return _form(_ORD_LT20[number], gender)
    if number < 100:
        tens, rest = divmod(number, 10)
        head = _form(_ORD_TENS[tens], gender)
        return head if rest == 0 else f"{head} {ordinal(rest, gender)}"
    if number < 1000:
        hundreds, rest = divmod(number, 100)
        if rest == 0:
            return _form(_ORD_HUNDREDS[hundreds], gender)
        return f"{_HUNDREDS[hundreds]} {ordinal(rest, gender)}"
    thousands, rest = divmod(number, 1000)
    if rest == 0:
        return _exact_thousands(thousands, gender)
    return f"{_thousand_phrase(thousands)} {ordinal(rest, gender)}"


def ordinal_locative_feminine(number: int) -> str:
    """Feminine locative, for a clock hour. ``18`` → ``osiemnastej``."""
    return " ".join(_locative(token) for token in ordinal(number, "f").split())


def decimal_phrase(integer: int, fraction_digits: str) -> str:
    """``3`` and ``"5"`` → ``trzy i pięć dziesiątych``. More than three places
    are read digit by digit after ``przecinek``.
    """
    if integer < 0 or not fraction_digits.isdigit() or fraction_digits == "":
        raise ValueError("decimal phrase needs a non-negative integer and digits")
    places = len(fraction_digits)
    if places > 3:
        digits = " ".join(cardinal(int(char)) for char in fraction_digits)
        return f"{cardinal(integer)} przecinek {digits}"
    numerator = int(fraction_digits)
    unit = _FRACTION[places][_paucal(numerator)]
    return f"{cardinal(integer)} i {cardinal_feminine(numerator)} {unit}"


def clock_phrase(hour: int, minute: int) -> str:
    """Feminine locative hour, cardinal minutes. ``14, 30`` → ``czternastej trzydzieści``."""
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("clock time out of range")
    spoken_hour = ordinal_locative_feminine(hour)
    if minute == 0:
        return spoken_hour
    return f"{spoken_hour} {cardinal(minute)}"


def parse_roman(token: str) -> int | None:
    """Canonical Roman value in 1-3999, or ``None`` when ``token`` is not one.

    ``IIII``, ``IC``, and ``IT`` are rejected. ``XIV`` is 14.
    """
    if not token or any(char not in _ROMAN_VALUE for char in token):
        return None
    total = 0
    index = 0
    while index < len(token):
        pair = token[index : index + 2]
        if pair in _SUBTRACTIVE:
            total += _SUBTRACTIVE[pair]
            index += 2
            continue
        if index + 1 < len(token) and _ROMAN_VALUE[token[index]] < _ROMAN_VALUE[token[index + 1]]:
            return None
        total += _ROMAN_VALUE[token[index]]
        index += 1
    if not 1 <= total <= 3999 or _format_roman(total) != token:
        return None
    return total


def numeral_suggestions(text: str, *, heading: bool = False) -> list[Suggestion]:
    """Numeral and ordinal-heading suggestions. ``text`` is not modified.

    A heading block (or a line that is only a Roman numeral) yields
    ``ordinal_heading``. Other readings are ``numeral``.
    """
    occupied = bytearray(len(text))
    found: list[Suggestion] = []
    _claim_headings(text, occupied, found, heading=heading)
    _claim_clocks(text, occupied, found)
    _claim_decimals(text, occupied, found)
    _claim_romans(text, occupied, found, heading=heading)
    _claim_dotted(text, occupied, found, heading=heading)
    _claim_integers(text, occupied, found, heading=heading)
    found.sort(key=lambda item: (item.start, item.end, item.reason))
    return found


def _scaled(number: int, scale: int, one: str, few: str, many: str) -> str:
    count, rest = divmod(number, scale)
    head = one if count == 1 else f"{cardinal(count)} {_noun(count, one, few, many)}"
    return head if rest == 0 else f"{head} {cardinal(rest)}"


def _noun(count: int, one: str, few: str, many: str) -> str:
    last_two = count % 100
    last = count % 10
    if (last_two < 10 or last_two > 20) and last == 1:
        return one
    if (last_two < 10 or last_two > 20) and last in {2, 3, 4}:
        return few
    return many


def _form(forms: tuple[str, str, str], gender: Gender) -> str:
    return forms[_GENDER_INDEX[gender]]


def _thousand_phrase(thousands: int) -> str:
    if thousands == 1:
        return "tysiąc"
    return f"{cardinal(thousands)} {_noun(thousands, 'tysiąc', 'tysiące', 'tysięcy')}"


def _compound_stem(number: int) -> str:
    if number < 10:
        return _UNIT_STEM[number]
    if number < 20:
        return _TEEN_STEM[number]
    if number < 100:
        tens, rest = divmod(number, 10)
        return _TENS_STEM[tens] + (_UNIT_STEM[rest] if rest else "")
    hundreds, rest = divmod(number, 100)
    return _HUNDRED_STEM[hundreds] + (_compound_stem(rest) if rest else "")


def _exact_thousands(thousands: int, gender: Gender) -> str:
    stem = "" if thousands == 1 else _compound_stem(thousands)
    suffix = {"m": "y", "f": "a", "n": "e"}[gender]
    return f"{stem}tysięczn{suffix}"


def _locative(token: str) -> str:
    if token.endswith("ga"):
        return token[:-2] + "giej"
    if token.endswith("ka"):
        return token[:-2] + "kiej"
    if token.endswith("a"):
        return token[:-1] + "ej"
    return token


def _paucal(number: int) -> int:
    if number % 10 == 1 and number % 100 != 11:
        return 0
    if number % 10 in {2, 3, 4} and number % 100 not in {12, 13, 14}:
        return 1
    return 2


def _format_roman(number: int) -> str:
    parts: list[str] = []
    remaining = number
    for value, glyph in _ROMAN_FORMAT:
        while remaining >= value:
            parts.append(glyph)
            remaining -= value
    return "".join(parts)


def _next_word(text: str) -> str | None:
    match = _NEXT_WORD.match(text)
    if match is None:
        return None
    return match.group(1)


def _previous_word(text: str) -> str | None:
    match = _PREV_WORD.search(text)
    if match is None:
        return None
    return match.group(1)


def _gender_of(word: str | None) -> Gender | None:
    if word is None:
        return None
    return _NOUN_GENDER.get(word.casefold())


def _bare(text: str, token: str) -> bool:
    stripped = text.strip()
    return stripped == token or stripped == f"{token}."


def _add(
    text: str,
    occupied: bytearray,
    found: list[Suggestion],
    start: int,
    end: int,
    replacement: str,
    kind: str,
    reason: str,
    confidence: float,
) -> None:
    if end <= start or any(occupied[start:end]) or text[start:end] == replacement:
        return
    occupied[start:end] = b"\x01" * (end - start)
    found.append(
        make_suggestion(
            text=text,
            start=start,
            end=end,
            replacement=replacement,
            kind=kind,
            reason=reason,
            confidence=confidence,
        )
    )


def _claim_headings(
    text: str, occupied: bytearray, found: list[Suggestion], *, heading: bool
) -> None:
    for match in _HEADING_RE.finditer(text):
        token = match.group(2)
        number = int(token) if token.isdigit() else parse_roman(token)
        if number is None:
            continue
        gender = _HEADING_WORDS[match.group(1).casefold()]
        at_start = text[: match.start()].strip() == ""
        kind = _HEADING if heading or at_start else _NUMERAL
        _add(
            text,
            occupied,
            found,
            match.start(),
            match.end(),
            f"{match.group(1)} {ordinal(number, gender)}",
            kind,
            "heading_ordinal",
            0.93,
        )


def _claim_clocks(text: str, occupied: bytearray, found: list[Suggestion]) -> None:
    for match in _CLOCK_RE.finditer(text):
        hour = int(match.group(1))
        minute = int(match.group(2))
        if hour > 23 or minute > 59:
            continue
        _add(
            text,
            occupied,
            found,
            match.start(),
            match.end(),
            clock_phrase(hour, minute),
            _NUMERAL,
            "clock",
            0.96,
        )


def _claim_decimals(text: str, occupied: bytearray, found: list[Suggestion]) -> None:
    for match in _DECIMAL_RE.finditer(text):
        _add(
            text,
            occupied,
            found,
            match.start(),
            match.end(),
            decimal_phrase(int(match.group(1)), match.group(2)),
            _NUMERAL,
            "decimal",
            0.95,
        )


def _claim_romans(
    text: str, occupied: bytearray, found: list[Suggestion], *, heading: bool
) -> None:
    for match in _ROMAN_RE.finditer(text):
        token = match.group(1)
        number = parse_roman(token)
        if number is None:
            continue
        following = _gender_of(_next_word(text[match.end() :]))
        preceding = _gender_of(_previous_word(text[: match.start()]))
        licensed = following is not None or preceding is not None
        bare = _bare(text, token)
        # Leading only: „Washington DC” must not treat DC as a heading numeral.
        leading = text[: match.start()].strip() == ""
        if (heading and (bare or leading)) or (bare and len(token) >= 2):
            kind = _HEADING
        elif licensed or len(token) >= 3:
            kind = _NUMERAL
        else:
            continue
        gender = following or preceding or "m"
        reason = "heading_ordinal" if kind == _HEADING else "roman"
        _add(
            text,
            occupied,
            found,
            match.start(),
            match.end(),
            ordinal(number, gender),
            kind,
            reason,
            0.9 if kind == _HEADING else 0.86,
        )


def _claim_dotted(
    text: str, occupied: bytearray, found: list[Suggestion], *, heading: bool
) -> None:
    for match in _DOTTED_RE.finditer(text):
        gender = _dotted_gender(text, match.start(), match.end())
        if gender is None:
            continue
        number = int(match.group(1))
        if number > 999_999:
            continue
        bare = _bare(text, match.group(0))
        kind = _HEADING if heading and bare else _NUMERAL
        _add(
            text,
            occupied,
            found,
            match.start(),
            match.end(),
            ordinal(number, gender),
            kind,
            "heading_ordinal" if kind == _HEADING else "ordinal",
            0.9 if kind == _HEADING else 0.88,
        )


def _dotted_gender(text: str, start: int, end: int) -> Gender | None:
    rest = text[end:]
    if rest.strip() == "":
        # „12.” on its own is an ordinal. „Zostało 5.” is a sentence period.
        if text[:start].strip() == "":
            return "m"
        return None
    word = _next_word(rest)
    if word is None:
        return "m"
    known = _gender_of(word)
    if known is not None:
        return known
    # „5. Potem” is a sentence boundary, not an ordinal dot.
    if word[:1].isupper():
        return None
    return "m"


def _claim_integers(
    text: str, occupied: bytearray, found: list[Suggestion], *, heading: bool
) -> None:
    for match in _INTEGER_RE.finditer(text):
        raw = match.group(1)
        grouped = " " in raw or "\u00a0" in raw
        number = int(raw.replace(" ", "").replace("\u00a0", ""))
        if number > _MAX_CARDINAL:
            continue
        bare = _bare(text, raw)
        if heading and bare and not grouped and number <= 999_999:
            replacement = ordinal(number, "m")
            kind = _HEADING
            reason = "heading_ordinal"
            confidence = 0.93
        elif not grouped and _is_year(number, text, match.end()):
            replacement = ordinal(number, "m")
            kind = _NUMERAL
            reason = "year"
            confidence = 0.9
        else:
            replacement = cardinal(number)
            kind = _NUMERAL
            reason = "cardinal"
            confidence = 0.95
        _add(
            text,
            occupied,
            found,
            match.start(),
            match.end(),
            replacement,
            kind,
            reason,
            confidence,
        )


def _is_year(number: int, text: str, end: int) -> bool:
    if not 1000 <= number <= 2099:
        return False
    word = _next_word(text[end:])
    return word is None or word.casefold() not in _QUANTITIES
