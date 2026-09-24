# .vulture_whitelist.py
# Whitelist for legitimate framework-managed attributes and utilities
from heathen_ledger.database import init_db
from heathen_ledger.models import User

# SQLAlchemy relationship attributes accessed via ORM queries
User.expense_contributions
User.payments_sent
User.payments_received

# Utility function for direct database initialization without Alembic
init_db
