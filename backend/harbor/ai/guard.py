"""Guardrails: number validator, template fallback and the AI-offline path.

Claude may only repeat numbers that already exist in the plan snapshot the rules engine built.
`validate` finds every number in the AI's text and reports the ones it can't trace back to the
snapshot. `guarded` runs a generator, retries once on a violation or error, then falls back to
the deterministic template, so the user always gets an answer with correct numbers.

What counts as "in the snapshot":
- every number value, rounded to 0, 1 or 2 decimal places ("$3" may cite 2.86)
- `*_cents` fields also as dollars (128000 -> 1,280)
- probabilities between 0 and 1 also as percentages (0.23 -> 23%)
- every number written inside a snapshot display string ("Mon 3:45 pm ET", "T+1")
- for ISO timestamps, only the year and the day of the month (local times come from display strings)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Callable, Generic, Iterable, Literal, TypeVar

T = TypeVar("T")

# A number, optionally with $ in front, thousands commas, decimals and a trailing %.
NUMBER_RE = re.compile(r"(?<![\w.])\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?%?|(?<![\w.])\$?\d+(?:\.\d+)?%?")
ISO_RE = re.compile(r"^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})(?:T[\d:.]+(?:Z|[+-]\d{2}:\d{2})?)?$")
ALWAYS_OK = {Decimal(0), Decimal(1)}


def _to_decimal(token: str) -> Decimal | None:
    try:
        return Decimal(token.strip("$%").replace(",", ""))
    except InvalidOperation:
        return None


def _variants(value: Decimal) -> set[Decimal]:
    out = {value}
    for places in ("1", "0.1", "0.01"):
        out.add(value.quantize(Decimal(places), rounding=ROUND_HALF_UP))
    return out


def allowed_numbers(snapshot: Any) -> set[Decimal]:
    allowed: set[Decimal] = set(ALWAYS_OK)

    def walk(node: Any, key: str = "") -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                walk(v, str(k))
        elif isinstance(node, (list, tuple, set, frozenset)):
            for v in node:
                walk(v, key)
        elif isinstance(node, bool) or node is None:
            return
        elif isinstance(node, (int, float, Decimal)):
            value = Decimal(str(node))
            allowed.update(_variants(value))
            if key.endswith("_cents"):
                allowed.update(_variants(value / 100))
            if 0 < value < 1:
                allowed.update(_variants(value * 100))
        elif isinstance(node, str):
            iso = ISO_RE.match(node)
            if iso:  # machine timestamps: only the year and day of month read naturally ("Oct 8, 2024")
                allowed.update({Decimal(iso["year"]), Decimal(int(iso["day"]))})
                return
            for token in NUMBER_RE.findall(node):
                d = _to_decimal(token)
                if d is not None:
                    allowed.update(_variants(d))

    walk(snapshot)
    return allowed


def numbers_in(text: str) -> list[str]:
    return NUMBER_RE.findall(text)


def validate(texts: Iterable[str], snapshot: Any) -> list[str]:
    """Numbers in `texts` that don't come from the snapshot. An empty list means the text is safe."""
    allowed = allowed_numbers(snapshot)
    bad = []
    for text in texts:
        for token in numbers_in(text):
            d = _to_decimal(token)
            if d is not None and d not in allowed:
                bad.append(token)
    return bad


@dataclass
class GuardResult(Generic[T]):
    value: T
    source: Literal["claude", "template"]
    violations: list[str] = field(default_factory=list)
    error: str | None = None


def guarded(
    generate: Callable[[], T] | None,
    texts_of: Callable[[T], Iterable[str]],
    template: Callable[[], T],
    snapshot: Any,
    attempts: int = 2,
) -> GuardResult[T]:
    """Run `generate` (the Claude call); keep its result only if every number checks out.

    Pass `generate=None` when the AI is switched off or has no key: the template is used directly.
    """
    violations: list[str] = []
    error = None
    if generate is not None:
        for _ in range(attempts):
            try:
                result = generate()
            except Exception as exc:  # timeouts, refusals, bad JSON: all fall back
                error = f"{type(exc).__name__}: {exc}"
                continue
            violations = validate(texts_of(result), snapshot)
            if not violations:
                return GuardResult(result, "claude")
    return GuardResult(template(), "template", violations, error)
