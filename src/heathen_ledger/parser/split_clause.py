import re
from ..dto import SplitSpec, ParseErrorResult
from .user_token import UserTokenParser


class SplitClauseParser:
    """Parses 'split' / 'among' clauses into typed SplitSpec objects."""

    EXCEPT_REGEX = re.compile(r"^(?:all\s+)?except\s+(.*)$", re.IGNORECASE)

    @classmethod
    def parse_clause(
        cls, clause_text: str
    ) -> tuple[SplitSpec | None, ParseErrorResult | None]:
        """Parses split clause content.

        Returns (SplitSpec, None) on success, or (None, ParseErrorResult) on error.
        """
        split_raw = clause_text.strip()
        exc_match = cls.EXCEPT_REGEX.match(split_raw)
        if exc_match:
            exc_tokens = exc_match.group(1).split()
            excluded = []
            for tok in exc_tokens:
                parsed_tok = UserTokenParser.parse_token(tok)
                if not parsed_tok:
                    return None, ParseErrorResult(
                        f"Invalid username '{tok}' in 'except' split."
                    )
                excluded.append(parsed_tok[0])
            return (
                SplitSpec(mode="except", excluded=excluded, participants=[]),
                None,
            )

        if split_raw.lower() in ("all", "everyone"):
            return SplitSpec(mode="all", participants=[]), None

        tokens = split_raw.split()
        shares = {}
        has_custom_shares = False
        participants_list = []
        for tok in tokens:
            parsed_tok = UserTokenParser.parse_token(tok)
            if not parsed_tok:
                return None, ParseErrorResult(
                    f"Invalid participant token '{tok}' in 'split' clause."
                )
            username, share_amt = parsed_tok
            participants_list.append(username)
            shares[username] = share_amt
            if share_amt is not None:
                has_custom_shares = True

        if has_custom_shares:
            return (
                SplitSpec(
                    mode="custom",
                    shares=shares,
                    participants=participants_list,
                ),
                None,
            )
        else:
            return (
                SplitSpec(
                    mode="subset",
                    participants=participants_list,
                ),
                None,
            )
