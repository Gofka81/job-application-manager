# Third-party attribution

## career-ops

<https://github.com/santifer/career-ops> — MIT, Copyright (c) 2026 Santiago
Fernández de Valderrama.

`hub/factgate.py` is a Python reimplementation of the approach in
`verify-cv-facts.mjs`: extract claims from a generated document, check them
against the source, and run the same extractor over both sides so widening a
pattern can only ever surface more claims rather than hide one.

The edge cases in `tests/test_factgate.py` are carried over from that
project's own tests, each one a real bug found in its review:

- a magnitude suffix must expand rather than truncate, or `50k` compares equal
  to `50` and a 1000x inflation passes the gate
- non-ASCII digits must fold, or a CV written in Arabic-Indic or Devanagari
  numerals yields zero claims and the gate reports a pass having checked
  nothing
- a capitalised trigger must not be the only spelling matched, or the exact
  form CVs are written in becomes invisible

No code was copied verbatim. `docs/research.md` records what else was read
there and what was deliberately not taken.
