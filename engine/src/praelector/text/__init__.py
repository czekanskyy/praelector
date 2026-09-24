# SPDX-License-Identifier: Apache-2.0
"""Text preparation: the lector's plain text and the deterministic pre-pass.

``plain`` turns a chapter into editor text and back (ED-02). ``prepass``
emits suggestions for artefacts, skip spans, dialogue splits, numerals, and
lexical tokens, speaker gender, and lexicon hits (AI-02, AI-09, DG-01…DG-06).
It does not change block text.
"""
