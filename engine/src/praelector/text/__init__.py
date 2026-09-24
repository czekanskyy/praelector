# SPDX-License-Identifier: Apache-2.0
"""Text preparation: the lector's plain text and the deterministic pre-pass.

``plain`` turns a chapter into editor text and back (ED-02). ``prepass``
emits suggestions for artefacts, skip spans, dialogue splits, numerals, and
lexical tokens, and speaker gender (AI-02, DG-01…DG-06). It does not change
block text. The lexicon is a later milestone.
"""
