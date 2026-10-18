"""Safe arithmetic evaluation. No eval(), no exec(), no exceptions escaping untyped."""

from __future__ import annotations

import math
import re


class CalcError(Exception):
    """Raised for any malformed or undefined expression."""


_TRANSLATION = {"×": "*", "·": "*", "÷": "/", "−": "-", "–": "-", "—": "-", "＋": "+"}
_WHITESPACE = re.compile(r"\s+")


def normalize(expr: str) -> str:
    """Canonical form of an expression: ASCII operators, no spaces."""
    out = []
    for ch in expr:
        out.append(_TRANSLATION.get(ch, ch))
    return _WHITESPACE.sub("", "".join(out))


def evaluate(expr: str):
    """Evaluate an expression and return a float. Raises CalcError."""
    parser = _Parser(normalize(expr))
    value = parser.parse()
    if not math.isfinite(value):
        raise CalcError("Result is out of range")
    return value


class _Parser:
    """Recursive-descent parser.

    expr    := term (('+' | '-') term)*
    term    := unary (('*' | '/') unary)*
    unary   := ('+' | '-') unary | power
    power   := postfix ('^' unary)?      -- right associative
    postfix := primary '%'*              -- percent is postfix /100
    primary := NUMBER | '(' expr ')'
    """

    def __init__(self, source: str) -> None:
        self.source = source
        self.pos = 0

    def parse(self) -> float:
        if not self.source:
            raise CalcError("Nothing to calculate")
        value = self._expression()
        if self._peek() is not None:
            raise CalcError(f"Unexpected '{self._peek()}'")
        return value

    # -- internals ---------------------------------------------------------

    def _peek(self) -> str | None:
        if self.pos < len(self.source):
            return self.source[self.pos]
        return None

    def _take(self) -> str:
        ch = self._peek()
        if ch is None:
            raise CalcError("Expression ended too early")
        self.pos += 1
        return ch

    def _accept(self, *chars: str) -> str | None:
        if self._peek() in chars:
            return self._take()
        return None

    def _expect(self, char: str) -> None:
        if self._take() != char:
            raise CalcError(f"Expected '{char}'")

    def _expression(self) -> float:
        value = self._term()
        while (op := self._accept("+", "-")) is not None:
            rhs = self._term()
            value = value + rhs if op == "+" else value - rhs
        return value

    def _term(self) -> float:
        value = self._unary()
        while (op := self._accept("*", "/")) is not None:
            rhs = self._unary()
            if op == "*":
                value *= rhs
            else:
                if rhs == 0:
                    raise CalcError("Cannot divide by zero")
                value /= rhs
        return value

    def _unary(self) -> float:
        if self._accept("-") is not None:
            return -self._unary()
        if self._accept("+") is not None:
            return self._unary()
        return self._power()

    def _power(self) -> float:
        base = self._postfix()
        if self._accept("^") is not None:
            exponent = self._unary()  # right associative, allows 2^-1
            try:
                return float(base ** exponent)
            except OverflowError as exc:
                raise CalcError("Result is out of range") from exc
        return base

    def _postfix(self) -> float:
        value = self._primary()
        while self._accept("%") is not None:
            value /= 100.0
        return value

    def _primary(self) -> float:
        if self._accept("(") is not None:
            value = self._expression()
            self._expect(")")
            return value
        return self._number()

    def _number(self) -> float:
        start = self.pos
        seen_dot = False
        while (ch := self._peek()) is not None and (ch.isdigit() or ch == "."):
            if ch == ".":
                if seen_dot:
                    raise CalcError("Malformed number")
                seen_dot = True
            self._take()
        if self.pos == start:
            raise CalcError("Expected a number")
        try:
            return float(self.source[start:self.pos])
        except ValueError as exc:
            raise CalcError("Malformed number") from exc


def format_result(value: float) -> str:
    """Human-friendly number rendering for the display."""
    if value == 0:
        return "0"
    if value == int(value) and abs(value) < 1e16:
        return str(int(value))
    rounded = round(value, 10)
    text = f"{rounded:.10f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "") else text


_TRAILING_SIGNED = re.compile(r"\(-(\d+\.?\d*)\)$")
_TRAILING_NUMBER = re.compile(r"(\d+\.?\d*)$")


def toggle_sign(buffer: str) -> str:
    """Negate (or un-negate) the number currently being edited."""
    match = _TRAILING_SIGNED.search(buffer)
    if match:
        return buffer[: match.start()] + match.group(1)
    match = _TRAILING_NUMBER.search(buffer)
    if match:
        return buffer[: match.start()] + "(-" + match.group(1) + ")"
    return buffer + "-" if buffer else "-"


def is_valid_continuation(buffer: str, char: str) -> bool:
    """Lightweight input rules so the buffer never starts with nonsense."""
    if char in "+-×÷%^":
        return bool(buffer) or char == "-"
    return True
