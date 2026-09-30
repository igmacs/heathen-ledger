import re

from ..domain.calculations import split_amount_equally
from ..dto import ParsedPayCommand, ParseErrorResult, SplitSpec
from .amount import AmountParser
from .date_clause import DateClauseParser
from .payer_clause import PayerClauseParser
from .split_clause import SplitClauseParser


class PayCommandParser:
    """Orchestrates parsing of /pay command messages."""

    KW_REGEX = re.compile(
        r"\b(for|by|split|among|on)\b|\bwith\b(?=\s+(?:@|me\b))", re.IGNORECASE
    )

    @classmethod
    def parse(cls, text: str) -> ParsedPayCommand | ParseErrorResult:
        """Parses a /pay command message to extract expense details."""
        # 1. Strip the /pay or /pay_persistent command prefix
        cleaned_text = re.sub(
            r"^/pay(?:_persistent)?(?:@\w+)?(?:\s+|$)", "", text, flags=re.IGNORECASE
        ).strip()
        if not cleaned_text:
            return ParseErrorResult("No valid amount found in the message.")

        # 2 & 3. Extract clauses and placeholders
        prefix_text, clauses, placeholders = cls._extract_clauses(cleaned_text)

        # 4. Parse Date Clause
        expense_date, err = cls._parse_date_clause(clauses)
        if err:
            return err

        # 5. Parse Split Clause
        split_spec, err = cls._parse_split_clause(clauses)
        if err:
            return err

        # 6. Parse Description Clause
        description, split_spec = cls._resolve_description_and_split(
            clauses, placeholders, split_spec
        )

        # 7. Parse Raw Payers
        raw_payers, err = cls._parse_payers_clause(clauses)
        if err:
            return err

        # 8 & 9. Resolve Amount and Finalize Payers
        amount_res = cls._resolve_final_amount_and_payers(
            prefix_text, raw_payers, split_spec
        )
        if isinstance(amount_res, ParseErrorResult):
            return amount_res
        amount_cents, payers, payer_username = amount_res

        # 10. Finalize Custom Split Shares
        custom_err = cls._finalize_custom_splits(split_spec, amount_cents)
        if custom_err:
            return custom_err

        return ParsedPayCommand(
            amount=amount_cents,
            payers=payers,
            description=description,
            split_spec=split_spec,
            expense_date=expense_date,
            payer_username=payer_username,
            participants=list(split_spec.participants),
        )

    @classmethod
    def _extract_clauses(
        cls, cleaned_text: str
    ) -> tuple[str, dict[str, str], dict[str, str]]:
        placeholders: dict[str, str] = {}

        def replace_quoted(m: re.Match) -> str:
            key = f"__QUOTED_DESC_{len(placeholders)}__"
            placeholders[key] = m.group(2)
            return f"for {key}"

        text = re.sub(
            r"\bfor\s+([\"'])(.*?)\1", replace_quoted, cleaned_text, flags=re.IGNORECASE
        )

        matches = list(cls.KW_REGEX.finditer(text))
        if not matches:
            return text, {}, placeholders

        prefix_text = text[: matches[0].start()].strip()
        clauses: dict[str, str] = {}
        for i, m in enumerate(matches):
            kw = m.group(1) or "split"  # 'with' maps to 'split'
            kw = kw.lower()
            if kw == "among":
                kw = "split"
            start = m.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            clauses[kw] = text[start:end].strip()

        return prefix_text, clauses, placeholders

    @classmethod
    def _parse_date_clause(cls, clauses: dict[str, str]):
        if "on" in clauses:
            return DateClauseParser.parse_clause(clauses["on"])
        return None, None

    @classmethod
    def _parse_split_clause(
        cls, clauses: dict[str, str]
    ) -> tuple[SplitSpec, ParseErrorResult | None]:
        if "split" in clauses:
            spec, err = SplitClauseParser.parse_clause(clauses["split"])
            if err:
                return SplitSpec(mode="all", participants=[]), err
            if spec:
                return spec, None
        return SplitSpec(mode="all", participants=[]), None

    @classmethod
    def _resolve_description_and_split(
        cls,
        clauses: dict[str, str],
        placeholders: dict[str, str],
        split_spec: SplitSpec,
    ) -> tuple[str | None, SplitSpec]:
        if "for" not in clauses:
            return None, split_spec

        for_raw = clauses["for"].strip()
        for placeholder, original in placeholders.items():
            if placeholder in for_raw:
                return for_raw.replace(placeholder, original).strip(), split_spec

        tokens = for_raw.split()
        all_mentions = bool(tokens) and all(re.fullmatch(r"@\w+", t) for t in tokens)
        if all_mentions and "split" not in clauses:
            legacy_participants = [t.lstrip("@").lower() for t in tokens]
            return None, SplitSpec(mode="subset", participants=legacy_participants)

        mentions_in_for = [m.lower() for m in re.findall(r"@(\w+)", for_raw)]
        desc_cleaned = re.sub(r"@\w+", "", for_raw).strip()
        desc_cleaned = re.sub(r"\s+", " ", desc_cleaned)
        description = desc_cleaned if desc_cleaned else None

        if mentions_in_for and "split" not in clauses and not split_spec.participants:
            split_spec = SplitSpec(mode="subset", participants=mentions_in_for)

        return description, split_spec

    @classmethod
    def _parse_payers_clause(
        cls, clauses: dict[str, str]
    ) -> tuple[list[tuple[str, int | None]], ParseErrorResult | None]:
        if "by" in clauses:
            raw, err = PayerClauseParser.parse_raw_payers(clauses["by"])
            if err:
                return [], err
            return raw or [], None
        return [], None

    @classmethod
    def _resolve_amount(
        cls,
        prefix_text: str,
        raw_payers: list[tuple[str, int | None]],
        split_spec: SplitSpec,
    ) -> tuple[int | None, list[tuple[str, int | None]]]:
        amt_match = re.search(r"\b(\d+(?:\.\d{1,2})?)\b", prefix_text)
        if amt_match:
            amount_cents = AmountParser.parse_cents(amt_match.group(1))
            if not raw_payers:
                prefix_before_amt = prefix_text[: amt_match.start()]
                payer_match = re.search(r"@(\w+)", prefix_before_amt)
                if payer_match:
                    raw_payers = [(payer_match.group(1).lower(), None)]
            return amount_cents, raw_payers

        if raw_payers and all(a is not None for _, a in raw_payers):
            return sum(a for _, a in raw_payers if a is not None), raw_payers

        if split_spec.mode == "custom" and all(
            a is not None for a in split_spec.shares.values()
        ):
            return sum(
                a for a in split_spec.shares.values() if a is not None
            ), raw_payers

        return None, raw_payers

    @classmethod
    def _resolve_final_amount_and_payers(
        cls,
        prefix_text: str,
        raw_payers: list[tuple[str, int | None]],
        split_spec: SplitSpec,
    ) -> tuple[int, dict[str, int], str | None] | ParseErrorResult:
        amount_cents, raw_payers = cls._resolve_amount(
            prefix_text, raw_payers, split_spec
        )
        if amount_cents is None:
            return ParseErrorResult("No valid amount found in the message.")
        if amount_cents <= 0:
            return ParseErrorResult("Amount must be greater than zero.")

        payers, payer_username, err = PayerClauseParser.finalize_payers(
            raw_payers, amount_cents
        )
        if err:
            return err
        if payers is None:
            return ParseErrorResult("Failed to resolve payers.")

        return amount_cents, payers, payer_username

    @classmethod
    def _finalize_custom_splits(
        cls, split_spec: SplitSpec, amount_cents: int
    ) -> ParseErrorResult | None:
        if split_spec.mode != "custom":
            return None

        shares = split_spec.shares
        specified_sum = sum(a for a in shares.values() if a is not None)
        unspecified = [u for u, a in shares.items() if a is None]

        if not unspecified:
            if specified_sum != amount_cents:
                return ParseErrorResult(
                    f"Sum of split amounts (${specified_sum / 100:.2f}) "
                    f"does not match total expense amount (${amount_cents / 100:.2f})."
                )
            return None

        if specified_sum > amount_cents:
            return ParseErrorResult(
                f"Specified split amounts (${specified_sum / 100:.2f}) "
                f"exceed total expense amount (${amount_cents / 100:.2f})."
            )

        remaining = amount_cents - specified_sum
        unspecified_shares = split_amount_equally(remaining, len(unspecified))
        idx = 0
        for u in list(shares.keys()):
            if shares[u] is None:
                shares[u] = unspecified_shares[idx]
                idx += 1
        return None
