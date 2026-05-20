# Heathen Ledger

> *"It's not about money... well, actually, it is. But it's also about sending a message."*

Heathen Ledger is a Telegram bot designed to help you and your friends easily track and settle shared expenses within group chats.

Whether you're organizing a trip, sharing an apartment, or just splitting a dinner bill, Heathen Ledger keeps track of who paid what and calculates the simplest way for everyone to settle their debts.

## Features

- **Group Integration**: Simply add the bot to any Telegram group to start tracking shared expenses.
- **Expense Tracking**: Record who paid for what, the amount, and who was involved in the expense.
- **Smart Debt Simplification**: When it's time to settle up, the bot calculates the minimum number of transactions needed to clear all debts. No more complex webs of "who owes who."
- **Current Balances**: Instantly check how much you owe or are owed at any given time.

## How it Works

*Commands are conceptual and may evolve during development.*

1. **Add an Expense**:
   - `/pay @Alice 50 for Dinner` (Alice paid $50.00; split equally among all members of the group chat).
   - `/pay @Alice 50 for @Bob @Charlie` (Alice paid $50.00; split specifically between Bob and Charlie).
   - `/pay 12.50 for Pizza` (The sender paid $12.50; split equally among all members of the group chat).

   > [!IMPORTANT]
   > **User Auto-Registration:**
   > To split an expense or specify a payer using their Telegram username (e.g. `@Alice`), that user **must have sent at least one message in the group** since the bot was added.
   > The bot auto-registers users when they send messages. If a user is mentioned but has never interacted, the bot will return a warning asking them to send a message to register.

2. **Check Balances**:
   `/balances` (Shows a quick summary of everyone's net balance)

3. **Settle Up**:
   `/settle` (Calculates the most efficient way to pay back everyone)

## Development

*Tech stack and setup instructions to be determined as the project develops.*

### Vibe Coding & AI Generation

This project is intended to be "vibe coded" as much as possible. All code and commits in this repository are 100% AI-generated unless explicitly specified otherwise.

**Workflow Rule:** The AI assistant must commit code incrementally after completing each logical file or small feature, providing atomic and descriptive commits, rather than batching everything into a single large commit.
