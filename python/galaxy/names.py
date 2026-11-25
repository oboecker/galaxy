"""The procedural galaxy's default names: two or three syllables, 5 to 10
letters, from pools of onsets, vowels and codas. A project gives its own
generator in project.toml (`namer`), a function of a `random.Random`."""

from __future__ import annotations

import random

_ONSETS: list[str] = (
    [''] * 3
    + list('bdfghjklmnprstyvwz')
    + ['br', 'dr', 'fl', 'fr', 'gl', 'gr', 'kh', 'kr', 'pl', 'pr',
       'sh', 'sk', 'sl', 'sm', 'sn', 'sp', 'st', 'th', 'tr']
)
_ONSETS_AFTER_CODA: list[str] = [''] * 3 + list('bdfghjklmnprstyvwz')
_VOWELS: list[str] = (
    ['a'] * 3 + ['e'] * 3 + ['i'] * 2 + ['o'] * 3 + ['u'] * 2
    + ['ai', 'ai', 'au', 'au', 'ea', 'ei', 'ei', 'ia', 'ia', 'ie', 'oi', 'ou', 'ou', 'ua', 'ui']
)
_CODAS_MID: list[str] = [''] * 4 + list('nrlm')
_CODAS_FINAL: list[str] = [''] * 2 + list('lmnrsk') + ['nd', 'nt', 'rd', 'rm', 'rn', 'st']
_CODAS_FINAL_LIGHT: list[str] = ['', '', '', 'n', 'r', 'l', 'm', 's']


def generate(rng: random.Random) -> str:
    """A name of two or three syllables, 5 to 10 letters. RuntimeError after
    100 failed tries."""
    for _ in range(100):
        n = rng.choices([2, 3], weights=[3, 1])[0]
        parts = []
        prev_coda = ''
        i = 0
        while i < n:
            onset = rng.choice(_ONSETS_AFTER_CODA if prev_coda else _ONSETS)
            if i == 0 and len(onset) > 1:
                n = 2  # a cluster at the start: two syllables at most
            vowel = rng.choice(_VOWELS)
            if i == n - 1:
                coda = rng.choice(_CODAS_FINAL_LIGHT if len(onset) > 1 else _CODAS_FINAL)
            else:
                coda = rng.choice(_CODAS_MID)
            parts.append(onset + vowel + coda)
            prev_coda = coda
            i += 1
        name = ''.join(parts)
        if 5 <= len(name) <= 10:
            return name.capitalize()
    raise RuntimeError("No name in 100 tries")
