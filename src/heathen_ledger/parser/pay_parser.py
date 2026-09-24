import re

from ..dto import ParsedPayCommand, ParseErrorResult, SplitSpec
from ..domain.calculations import split_amount_equally
from .amount import AmountParser
from .date_clause import DateClauseParser
from .split_clause import SplitClauseParser
from .payer_clause import PayerClauseParser


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

        # 2. Extract quoted descriptions to avoid keyword collision inside strings
        placeholders: dict[str, str] = {}

        def replace_quoted(m: re.Match) -> str:
            key = f"__QUOTED_DESC_{len(placeholders)}__"
            placeholders[key] = m.group(2)
            return f"for {key}"

        cleaned_text = re.sub(
            r"\bfor\s+([\"'])(.*?)\1", replace_quoted, cleaned_text, flags=re.IGNORECASE
        )

        # 3. Identify keyword clause boundaries
        matches = list(cls.KW_REGEX.finditer(cleaned_text))
        clauses: dict[str, str] = {}
        if matches:
            prefix_text = cleaned_text[: matches[0].start()].strip()
            for i, m in enumerate(matches):
                kw = m.group(1) or "split"  # 'with' maps to 'split'
                kw = kw.lower()
                if kw == "among":
                    kw = "split"
                start = m.end()
                end = (
                    matches[i + 1].start()
                    if i + 1 < len(matches)
                    else len(cleaned_text)
                )
                clause_content = cleaned_text[start:end].strip()
                clauses[kw] = clause_content
        else:
            prefix_text = cleaned_text

        # 4. Parse Date Clause
        expense_date = None
        if "on" in clauses:
            expense_date, err = DateClauseParser.parse_clause(clauses["on"])
            if err:
                return err

        # 5. Parse Split Clause
        split_spec = SplitSpec(mode="all", participants=[])
        if "split" in clauses:
            split_spec_obj, err = SplitClauseParser.parse_clause(clauses["split"])
            if err:
                return err
            if split_spec_obj:
                split_spec = split_spec_obj

        # 6. Parse Description Clause
        description = None
        if "for" in clauses:
            for_raw = clauses["for"].strip()
            # Restore quoted description if present
            for placeholder, original in placeholders.items():
                if placeholder in for_raw:
                    for_raw = for_raw.replace(placeholder, original)
                    description = for_raw.strip()
                    break

            if description is None:
                # Check for legacy participant syntax: /pay 50 for @Bob @Charlie
                tokens = for_raw.split()
                all_mentions = bool(tokens) and all(
                    re.fullmatch(r"@\w+", t) for t in tokens
                )
                if all_mentions and "split" not in clauses:
                    legacy_participants = [t.lstrip("@").lower() for t in tokens]
                    split_spec = SplitSpec(
                        mode="subset",
                        participants=legacy_participants,
                    )
                    description = None
                else:
                    # Description with potential inline mentions (legacy: /pay 12.50 for lunch @Bob)
                    mentions_in_for = [
                        m.lower() for m in re.findall(r"@(\w+)", for_raw)
                    ]
                    desc_cleaned = re.sub(r"@\w+", "", for_raw).strip()
                    desc_cleaned = re.sub(r"\s+", " ", desc_cleaned)
                    description = desc_cleaned if desc_cleaned else None
                    if (
                        mentions_in_for
                        and "split" not in clauses
                        and not split_spec.participants
                    ):
                        split_spec = SplitSpec(
                            mode="subset",
                            participants=mentions_in_for,
                        )

        # 7. Parse Raw Payers
        raw_payers = []
        if "by" in clauses:
            raw_payers_res, err = PayerClauseParser.parse_raw_payers(clauses["by"])
            if err:
                return err
            if raw_payers_res is not None:
                raw_payers = raw_payers_res

        # 8. Resolve Numeric Amount and Legacy Payer from Prefix
        amount_cents = None
        amt_match = re.search(r"\b(\d+(?:\.\d{1,2})?)\b", prefix_text)
        if amt_match:
            amount_cents = AmountParser.parse_cents(amt_match.group(1))
            if not raw_payers:
                prefix_before_amt = prefix_text[: amt_match.start()]
                payer_match = re.search(r"@(\w+)", prefix_before_amt)
                if payer_match:
                    legacy_payer = payer_match.group(1).lower()
                    raw_payers = [(legacy_payer, None)]

        # If amount was not in prefix, try inferring from custom payer amounts or custom splits
        if amount_cents is None:
            if raw_payers and all(a is not None for _, a in raw_payers):
                amount_cents = sum(a for _, a in raw_payers if a is not None)
            elif split_spec.mode == "custom" and all(
                a is not None for a in split_spec.shares.values()
            ):
                amount_cents = sum(
                    a for a in split_spec.shares.values() if a is not None
                )
            else:
                return ParseErrorResult("No valid amount found in the message.")

        if amount_cents <= 0:
            return ParseErrorResult("Amount must be greater than zero.")

        # 9. Finalize Payers
        payers, payer_username, err = PayerClauseParser.finalize_payers(
            raw_payers, amount_cents
        )
        if err:
            return err
        if payers is None:
            return ParseErrorResult("Failed to resolve payers.")

        # 10. Finalize Custom Split Shares
        if split_spec.mode == "custom":
            shares = split_spec.shares
            specified_sum = sum(a for a in shares.values() if a is not None)
            unspecified = [u for u, a in shares.items() if a is None]

            if not unspecified:
                if specified_sum != amount_cents:
                    return ParseErrorResult(
                        f"Sum of split amounts (${specified_sum / 100:.2f}) "
                        f"does not match total expense amount (${amount_cents / 100:.2f})."
                    )
            else:
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

        participants = list(split_spec.participants)

        return ParsedPayCommand(
            amount=amount_cents,
            payers=payers,
            description=description,
            split_spec=split_spec,
            expense_date=expense_date,
            payer_username=payer_username,
            participants=participants,
        )
