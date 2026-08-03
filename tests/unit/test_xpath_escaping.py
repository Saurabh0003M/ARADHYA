"""Regression tests for XPath literal escaping in browser_tools.

Guards the injection reported in the 2026-06-15 security audit: element text
was interpolated straight into an XPath predicate, so a crafted string such as
``' or '1'='1`` escaped the predicate and turned a targeted lookup into a
match-anything selector — causing a click on an arbitrary element.
"""

from __future__ import annotations

import pytest

from src.aradhya.tools.browser_tools import xpath_literal


class TestXpathLiteral:
    def test_plain_text_uses_single_quotes(self) -> None:
        assert xpath_literal("Sign in") == "'Sign in'"

    def test_text_with_apostrophe_switches_to_double_quotes(self) -> None:
        assert xpath_literal("it's") == '"it\'s"'

    def test_text_with_double_quote_uses_single_quotes(self) -> None:
        assert xpath_literal('say "hi"') == '\'say "hi"\''

    def test_both_quote_kinds_use_concat(self) -> None:
        result = xpath_literal("it's a \"test\"")
        assert result.startswith("concat(")
        assert '"\'"' in result  # the single-quote piece

    def test_injection_payload_is_neutralised(self) -> None:
        """The audit's proof-of-concept must not escape the predicate."""
        payload = "' or '1'='1"
        literal = xpath_literal(payload)
        expression = f"//*[contains(text(), {literal})]"

        # The payload's quotes must not terminate the literal early: the
        # expression must contain exactly one balanced literal, not an
        # injected `or` clause sitting outside quotes.
        assert expression.count("[") == 1
        assert expression.endswith(")]")
        # The dangerous unquoted form must NOT appear.
        assert "contains(text(), '' or '1'='1')" not in expression

    @pytest.mark.parametrize(
        "payload",
        [
            "' or '1'='1",
            "'] | //* | //*['",
            'x") or ("1"="1',
            "normal text",
            "with 'both' and \"kinds\"",
            "",
        ],
    )
    def test_quotes_are_balanced_for_arbitrary_input(self, payload: str) -> None:
        literal = xpath_literal(payload)
        if literal.startswith("concat("):
            return  # concat() form is balanced by construction
        quote = literal[0]
        assert literal[-1] == quote
        # The delimiter must not appear inside the literal body.
        assert quote not in literal[1:-1]

    def test_empty_string(self) -> None:
        assert xpath_literal("") == "''"
