from ..domain.calculations import split_amount_equally
from ..dto import ParseErrorResult
from .user_token import UserTokenParser


class PayerClauseParser:
    """Parses 'by' payer clauses and validates specified payer shares."""

    @classmethod
    def parse_raw_payers(
        cls, clause_text: str
    ) -> tuple[list[tuple[str, int | None]] | None, ParseErrorResult | None]:
        """Parses raw payer tokens from a 'by' clause."""
        tokens = clause_text.split()
        raw_payers = []
        for tok in tokens:
            parsed_tok = UserTokenParser.parse_token(tok)
            if not parsed_tok:
                return None, ParseErrorResult(
                    f"Invalid payer token '{tok}' in 'by' clause."
                )
            raw_payers.append(parsed_tok)
        return raw_payers, None

    @classmethod
    def finalize_payers(
        cls,
        raw_payers: list[tuple[str, int | None]],
        amount_cents: int,
    ) -> tuple[dict[str, int] | None, str | None, ParseErrorResult | None]:
        """Validates and distributes payer amounts.

        Returns (payers_dict, single_payer_username_or_none, error_or_none).
        """
        if not raw_payers:
            return {"me": amount_cents}, None, None

        specified_sum = sum(a for _, a in raw_payers if a is not None)
        unspecified = [u for u, a in raw_payers if a is None]

        payers: dict[str, int] = {}
        if not unspecified:
            if specified_sum != amount_cents:
                return (
                    None,
                    None,
                    ParseErrorResult(
                        f"Sum of payer amounts (${specified_sum / 100:.2f}) "
                        f"does not match total expense amount (${amount_cents / 100:.2f})."
                    ),
                )
            payers = {u: a for u, a in raw_payers if a is not None}
        else:
            if specified_sum > amount_cents:
                return (
                    None,
                    None,
                    ParseErrorResult(
                        f"Specified payer amounts (${specified_sum / 100:.2f}) "
                        f"exceed total expense amount (${amount_cents / 100:.2f})."
                    ),
                )
            remaining = amount_cents - specified_sum
            unspecified_shares = split_amount_equally(remaining, len(unspecified))
            idx = 0
            for u, a in raw_payers:
                if a is not None:
                    payers[u] = a
                else:
                    payers[u] = unspecified_shares[idx]
                    idx += 1

        single_payer = None
        if len(payers) == 1:
            first_user = next(iter(payers))
            single_payer = None if first_user == "me" else first_user

        return payers, single_payer, None
