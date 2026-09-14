"""Domain layer containing business logic, models, and calculation algorithms."""

from .calculations import split_amount_equally, simplify_debts

__all__ = ["split_amount_equally", "simplify_debts"]
