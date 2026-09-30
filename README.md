# Heathen Ledger (WIP)

> *"It's not about money... well, actually, it is. But it's also about sending a message."*

Heathen Ledger is a Telegram bot designed to help you and your friends easily track and settle shared expenses within group chats.

Whether you're organizing a trip, sharing an apartment, or just splitting a dinner bill, Heathen Ledger keeps track of who paid what and calculates the simplest way for everyone to settle their debts.

## Features

- **Group Integration**: Simply add the bot to any Telegram group to start tracking shared expenses.
- **Expense Tracking**: Record who paid for what, the amount, and who was involved in the expense.
- **Smart Debt Simplification**: When it's time to settle up, the bot calculates the minimum number of transactions needed to clear all debts. No more complex webs of "who owes who."
- **Current Balances**: Instantly check how much you owe or are owed at any given time.
- **Voice Commands**: Speak natural voice notes (e.g., *"I paid 25 for dinner"*) to automatically transcribe and interpret them into ledger commands via Google Gemini.
- **Receipt & Ticket Scanning**: Share a photo of a restaurant bill or store receipt to automatically extract and itemize line items, subtotal, tax, tip, and total via multimodal Google Gemini vision.

## How it Works

1. **Add an Expense**:
   - **Syntax**: `/pay <amount> [for <description>] [by <payer(s)>] [split <split_spec>] [on <date>]`
   - **Basic everyday use**:
     - `/pay 12.50 for Pizza` (Sender paid $12.50; split equally among all members of the group chat).
     - `/pay 50 for Dinner on 2026-09-07` (Sender paid $50.00 for Dinner on a specific date; defaults to today).
   - **Multiple or other payers (`by ...`)**:
     - `/pay 50 for Groceries by @Alice` (Alice paid $50.00; split equally among all members).
     - `/pay 90 for Dinner by me @Bob` (Sender and Bob paid $45.00 each from a joint account or shared cash).
     - `/pay 40 for Pizza by me:25 @Charlie:15` (Sender paid $25.00, Charlie paid $15.00).
   - **Splits & Beneficiaries (`split ...`)**:
     - `/pay 60 for escape room split @Alice @Bob` (Split equally only between Alice and Bob).
     - `/pay 30 for drinks split @Bob:10 @Charlie:20` (Custom shares: Bob owes $10.00, Charlie owes $20.00).
     - `/pay 45 for groceries split except @Dave` (Split equally among all members except Dave).
   - **Standalone Execution & Undo**:
     - The `/pay` command with parameters is standalone: it immediately logs the expense as specified and replies with a confirmation and a `🗑️ Undo` button. The creator of the expense can tap `🗑️ Undo` to delete the transaction if recorded by mistake.

   > [!IMPORTANT]
   > **User Registration & Privacy Mode:**
   > To split an expense or specify a payer using their Telegram username (e.g. `@Alice`), that user must be registered in the group ledger.
   > Because Telegram bots commonly operate with **Privacy Mode enabled** (where bots cannot see casual chat text messages), Heathen Ledger provides flexible registration methods:
   > - **Self-Registration Button**: Run `/register` with no parameters to post an interactive `[ 📝 Register me ]` button that any member can tap to join the group ledger instantly.
   > - **Mentioning Members**: Run `/register @username` (e.g. `/register @Alice` or `/register @Alice Alice Smith`), mention a user directly via text mention, or mention multiple members (`/register @alice @bob`). Group admins and known Telegram accounts resolve automatically, while other users are created as pending profiles that automatically link to their real Telegram accounts the moment they interact with the bot.
   > - **Replying to a Message**: Reply to any message sent by a group member with `/register` to register them on the spot.
   > - **External / Non-Telegram Members**: Run `/register <name>` (e.g. `/register John Doe`) to track expenses and settlements for people without Telegram accounts.

2. **Check Balances**:
   - `/balances` (Shows a summary of everyone's net balance, sorted from highest creditor to highest debtor).

3. **Settle Up**:
   - `/settle` (Calculates the minimum number of transactions needed to clear all debts using a greedy simplification algorithm).

4. **Record a Payback**:
   - `/payback @Alice 10` (Logs that you paid Alice $10.00).
   - `/payback @Bob @Alice 12.50` (Logs that Bob paid Alice $12.50).

5. **Audit History**:
   - `/history` (Displays the last 10 logged transactions—expenses and payments—in chronological order using Telegram Rich Messages with embedded delete buttons beside each entry).

6. **Close Ledger & Reset Group**:
   - `/close` (or `/close_ledger`): Once all debts are settled, closes the ledger, wipes the group's records and external guest profiles from the database, and causes the bot to leave the Telegram chat.
   - If open debts remain when `/close` is called, the bot prevents closure, displays the outstanding balances, and directs members to `/settle`.
   - To start a new ledger later, simply add the bot back to the group chat.

7. **Voice Messages**:
   - Send or forward a voice note to the chat (e.g., saying *"I paid 25 for dinner"* or *"Alice paid 50 for groceries"*).
   - Reply to the voice note with `/voice`, `/pay`, or tag the bot (`@HeathenLedgerBot`) to tell the bot that the audio is intended for it. Casual voice messages sent to the chat without a reply or mention are ignored.
   - The bot transcribes the audio using Google Gemini and displays the interpreted ledger command with interactive confirmation buttons:
      - `[ ❌ Reject ]`: Cancels the command without recording any changes to the ledger.

8. **Receipt & Ticket Scanning & Interactive Splitting**:
   - Send or forward a photo of a restaurant bill or store receipt to the chat.
   - Send the photo with caption `/ticket` (or `/receipt`), reply to an existing receipt photo with `/ticket`, or tag the bot (`@HeathenLedgerBot`) to parse it.
   - The bot downloads the image in memory and uses Google Gemini vision with structured Pydantic schemas to extract all individual line items (names, quantities, prices), subtotal, tax, tip, and total.
   - **Repeated Items Expansion**: When an item has a quantity greater than 1 (e.g., 5 beers), it is expanded into individual numbered entries (`Beer #1`, `Beer #2`, ...) with penny-perfect price rounding so friends can claim individual items independently.
   - **Interactive Claiming & User Initials**: Each line item features an embedded `[👤 +Me]` button. Tapping it toggles your claim, displaying your initials (e.g., `(👤 AL)` or `(👥 IG, AL)`) for immediate visual feedback. Items can be marked complete with `[✅]`, striking them through.
   - **Person-First Assignment & Multi-Item Checklist**: Instead of tedious per-item selection, tapping `[👥 Assign Other...]` opens a Person Selector listing group members, previously added external guests, and a button to register new guests. Entering an external guest's name once immediately opens an interactive checklist (`◻️`/`☑️`) showing all receipt items, where tapping items toggles that person's participation instantly. Guests remain remembered in the session so their items can be adjusted at any time without re-typing their names.
   - **Proportional Split & Ledger Recording**: Tapping `[🧾 Finish & Split]` calculates each person's exact share, allocating taxes, tips, discounts, and extra fees proportionally to their claimed items. Tapping `[💾 Record to Ledger]` logs the final expense directly into group balances via the standard ledger command engine.

9. **Members & Directory**:
   - `/members` (Lists all members in the current group ledger, tagging external non-Telegram members).
   - `/register` (Generates an interactive button for members to tap and register themselves).
   - `/register @handle [Display Name]` or `/register <name>` to register group members or external users. Once registered, they participate in all ledger flows (equal splits, custom shares, balances, paybacks, and debt settlements).

10. **Ephemeral Responses with Share & Dismiss Actions**:
   - **Ephemeral by Default**: All bot commands (`/pay`, `/balances`, `/settle`, `/history`, `/payback`, `/register`, `/members`, `/voice`, `/ticket`, `/close`, `/help`) are registered as ephemeral commands (`is_ephemeral=True` for `BotCommandScopeAllGroupChats`). When invoked from Telegram's `/` menu, both the command invocation and the bot's response are **ephemeral** (visible only to you), keeping busy group chats clean and uncluttered.
   - **Share to Group (`📢 Share to group`)**: Every ephemeral response includes an inline button to publish the message to the group. Tapping this button deletes the ephemeral preview and broadcasts the message publicly with all original operational buttons (such as settlement payback buttons, expense participant toggles, or registration buttons).
   - **Dismiss (`✕ Dismiss`)**: Every ephemeral response also includes an inline button allowing you to immediately delete the ephemeral message from your view when you are done reviewing it.

## Development

### Prerequisites
- Python 3.10+
- A Telegram Bot Token from [@BotFather](https://t.me/BotFather)

### Local Setup
1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   ```
2. Install the package in editable mode:
   ```bash
   pip install -e .
   ```
3. Create a `.env` file in the project root (you can copy `.env.example`):
   ```env
   TELEGRAM_BOT_TOKEN=your_bot_token_here
   GEMINI_API_KEY=your_gemini_api_key_here  # Optional: for voice interpretation and receipt scanning
   ```
4. Run Alembic migrations to set up the SQLite database schema:
   ```bash
   alembic upgrade head
   ```

### Running the Bot
Start the bot application:
```bash
python -m heathen_ledger.bot
```

### Running the Test Suite
Verify everything is working with:
```bash
python -m unittest discover -s tests
```

### Production Deployment

#### Option A: Docker Compose (Recommended)
This method ensures the bot runs inside a containerized environment and automatically restarts on system reboots.
1. Populate your root `.env` file with the target `TELEGRAM_BOT_TOKEN`.
2. Launch the containerized bot in detached mode:
   ```bash
   docker compose up -d --build
   ```
3. To view running logs:
   ```bash
   docker compose logs -f
   ```
The SQLite database file will be saved inside the docker volume `bot_data` (mapped to `/app/data` inside the container), keeping your ledger state persistent across upgrades.

#### Option B: systemd System Service
For native deployments on a Linux server without Docker:
1. Create a systemd service file at `/etc/systemd/system/heathen-ledger.service`:
   ```ini
   [Unit]
   Description=Heathen Ledger Telegram Bot
   After=network.target

   [Service]
   Type=simple
   User=your-ssh-user
   WorkingDirectory=/home/your-ssh-user/heathen-ledger
   EnvironmentFile=/home/your-ssh-user/heathen-ledger/.env
   ExecStart=/home/your-ssh-user/heathen-ledger/.venv/bin/python bot.py
   Restart=on-failure

   [Install]
   WantedBy=multi-user.target
   ```
2. Enable and start the service:
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable heathen-ledger
   sudo systemctl start heathen-ledger
   ```
3. Monitor the execution status or logs:
   ```bash
   sudo systemctl status heathen-ledger
   journalctl -u heathen-ledger -f
   ```

#### Option C: Automated Deployment (Ansible)
If you want to automate server configuration and bot deployment on a manually ordered VPS (like Infomaniak VPS Lite), you can use the provided Ansible script located in the `ansible/` directory.

1. **Prepare Server Configuration:**
   - Copy `ansible/inventory.ini.example` to `ansible/inventory.ini` and replace the placeholder IP with your server's IP. (Or use the active `inventory.ini` created during configuration).
   - Copy `ansible/vars.yml.example` to `ansible/vars.yml` and add your `TELEGRAM_BOT_TOKEN`.

2. **Run Ansible Playbook:**
   - Run the playbook to install Docker, configure the server, copy application files, and launch the bot:
     ```bash
     cd ansible
     ansible-playbook -i inventory.ini playbook.yml
     ```
