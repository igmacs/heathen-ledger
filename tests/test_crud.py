import sys
import os

# Add project root to path dynamically
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Base
import crud


def run_test():
    print("Initializing test database...")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)

    with Session() as session:
        # 1. Register group and users
        group = crud.get_or_create_group(session, 12345, "Trip to Spain")
        alice = crud.get_or_create_user(session, 11, "alice", "Alice")
        bob = crud.get_or_create_user(session, 22, "bob", "Bob")
        charlie = crud.get_or_create_user(session, 33, "charlie", "Charlie")

        # 2. Add users to group
        crud.add_user_to_group(session, alice, group)
        crud.add_user_to_group(session, bob, group)
        crud.add_user_to_group(session, charlie, group)
        session.commit()

        # Verify membership
        assert len(group.members) == 3, f"Expected 3 members, got {len(group.members)}"
        print("✓ Membership successfully verified.")

        # 3. Log a split expense
        # Alice paid 30.00 (3000 cents) for dinner, split equally between Alice, Bob, and Charlie (1000 each)
        splits = {alice.id: 1000, bob.id: 1000, charlie.id: 1000}
        crud.create_expense(
            session,
            group_id=group.id,
            payer_id=alice.id,
            amount=3000,
            description="Dinner",
            splits=splits,
        )
        session.commit()

        # Verify balances: Alice should be owed 20.00 (+2000), Bob and Charlie owe 10.00 (-1000) each.
        balances = crud.get_group_balances(session, group.id)
        assert (
            balances[alice.id] == 2000
        ), f"Expected Alice to have +2000, got {balances[alice.id]}"
        assert (
            balances[bob.id] == -1000
        ), f"Expected Bob to have -1000, got {balances[bob.id]}"
        assert (
            balances[charlie.id] == -1000
        ), f"Expected Charlie to have -1000, got {balances[charlie.id]}"
        print("✓ Expense split and balances successfully verified.")

        # 4. Log a settlement payment
        # Bob pays Alice 10.00 (1000 cents)
        crud.create_payment(
            session,
            group_id=group.id,
            payer_id=bob.id,
            payee_id=alice.id,
            amount=1000,
        )
        session.commit()

        # Verify updated balances: Bob is settled (0), Alice is owed 10.00 (+1000), Charlie owes 10.00 (-1000).
        balances = crud.get_group_balances(session, group.id)
        assert (
            balances[alice.id] == 1000
        ), f"Expected Alice to have +1000, got {balances[alice.id]}"
        assert balances[bob.id] == 0, f"Expected Bob to have 0, got {balances[bob.id]}"
        assert (
            balances[charlie.id] == -1000
        ), f"Expected Charlie to have -1000, got {balances[charlie.id]}"
        print("✓ Settlement payment and updated balances successfully verified.")

    print("All tests passed successfully!")


if __name__ == "__main__":
    run_test()
