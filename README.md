# Heathen Ledger

> *"It's not about money... well, actually, it is. But it's also about sending a message."*

Heathen Ledger is a Telegram bot designed to help you and your friends easily track and settle shared expenses within group chats.

Whether you're organizing a trip, sharing an apartment, or just splitting a dinner bill, Heathen Ledger keeps track of who paid what and calculates the simplest way for everyone to settle their debts.

## Features

- **Group Integration**: Simply add the bot to any Telegram group to start tracking shared expenses.
- **Expense Tracking**: Record who paid for what, the amount, and who was involved in the expense.
- **Smart Debt Simplification**: When it's time to settle up, the bot calculates the minimum number of transactions needed to clear all debts. No more complex webs of "who owes who."
- **Current Balances**: Instantly check how much you owe or are owed at any given time.
- **Voice Commands**: Speak natural voice notes (e.g., *"I paid 25 for dinner"*) to automatically transcribe and interpret them into ledger commands via Google Gemini.

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
   - **Interactive Toggles & Undo**:
     - After recording an expense, the bot shows inline buttons for all group members. The creator of the expense can tap these buttons to dynamically toggle members in/out of the split, which automatically recalculates and updates the shares, or tap `🗑️ Undo` to delete it.

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
   - `/history` (Displays the last 10 logged transactions—expenses and payments—in chronological order).

6. **Voice Messages**:
   - Send or forward a voice note to the chat (e.g., saying *"I paid 25 for dinner"* or *"Alice paid 50 for groceries"*).
   - Reply to the voice note with `/voice`, `/pay`, or tag the bot (`@HeathenLedgerBot`) to tell the bot that the audio is intended for it. Casual voice messages sent to the chat without a reply or mention are ignored.
   - The bot transcribes the audio using Google Gemini and displays the interpreted ledger command with interactive confirmation buttons:
     - `[ ✅ Confirm ]`: Executes the proposed command immediately in the group chat (recording expenses, paybacks, or generating summaries) and equips the response with interactive split toggles and undo buttons.
     - `[ ❌ Reject ]`: Cancels the command without recording any changes to the ledger.

7. **Members & Directory**:
   - `/members` (Lists all members in the current group ledger, tagging external non-Telegram members).
   - `/register` (Generates an interactive button for members to tap and register themselves).
   - `/register @handle [Display Name]` or `/register <name>` to register group members or external users. Once registered, they participate in all ledger flows (equal splits, custom shares, balances, paybacks, and debt settlements).

8. **Ephemeral Messages & Commands (PoC)**:
   - `/ephemeral` or `/whisper`: Demonstrates Telegram Bot API 10.2+ / 10.3+ two-way ephemeral commands and messages.
   - **Ephemeral Commands (Two-Way Privacy)**: Registered with `is_ephemeral=True` on `BotCommand` and scoped to group chats (`BotCommandScopeAllGroupChats`). When a user types `/` in a group and selects `/ephemeral` or `/whisper` from the autocomplete popup, Telegram transmits the command invocation ephemerally (`ephemeral_message_id`), rendering the command invisible to other group members. The bot replies directly within 15 seconds targeting `reply_parameters.ephemeral_message_id`, achieving complete two-way privacy **without requiring group administrator privileges**.
   - **Admin vs. Non-Admin Rules**: If invoked as a regular text message (or without incoming `ephemeral_message_id`), Telegram requires the bot to be a **chat administrator** to send an ephemeral reply. Non-admin bots can only send ephemeral messages within 15 seconds by supplying `reply_parameters.ephemeral_message_id` (from an incoming ephemeral command) or `callback_query_id` (from an inline button tap).

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
   GEMINI_API_KEY=your_gemini_api_key_here  # Optional: for voice message interpretation
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

### Vibe Coding & AI Generation

This project is intended to be "vibe coded" as much as possible. All code and commits in this repository are 100% AI-generated unless explicitly specified otherwise.

#### Project evolution & Agent conversation history

Here I document my conversation with the Antigravity agent and how the
project evolved, with emphasis in when was the agent autonomous and
when I had to correct or guide it

- I explained the project I wanted to build and asked the agent to
  create the README. I asked for a few a amends to include things I
  considered important, and finally to commit it. It did it well, the
  only problem is that it had a tendency to include in the commit
  messages a few words about my amend requests, even if they were not
  really important in comparison with my main request.

- I asked what languages and tools the agent recommended to build the
  bot, and we settled with Python. I asked it to create a Hello World
  Python Telegram bot skeleton, which it did mostly successfully,
  except for the following:
  - The bot token was hardcoded so I had to ask it to treat it as a
    secret.
  - I had to explicitly ask for dependency management

- I asked the agent to help me come up with some fun quotes for the
  projects, building on the play of words in the name (the actor Heath
  Ledger, in particular his role as The Joker in The Dark Knight film,
  and the concept of a ledger telegram bot). It came with surprisingly
  good suggestions, I have only used one for now but the other ones
  are saved for later and will probably be used later

- I asked it to proceed with the implementation and it tried to create
  the core logic of the bot all at once. It didn't go well
  - First, I had to remind it to create smaller and incremental
    commits, and to add a section somewhere to remind it in the
    future. It choose the README, so I'm skeptical it will be useful
  - I had to ask it why it had written and import in the middle of the
    code, and the agent moved it to the beginning of the file
  - I had to ask it to write a pre-commit configuration since it was
    adding trailing whitespaces everywhere. It suggested using ruff
    for formatting and I accepted it. The agent added the
    configuration and fixed the code autonomously
    - Although it added a check-yaml hook and there was no yaml file
      in the project nor any plan to have it, so I had to ask it to
      remove it
  - Then I tried the code, and it didn't work well, although I don't
    remember now how broken it was. I manually reverted commit 665b0d8
    but keeping all changes on top, the only change that I had made
    manually so far

- I asked to forget about the logic for now and start with the
  database, for which at some point we had agreed to use SQLite,
  although I don't remember when anymore. I had to correct the agent a
  few times here to
  - It created the db file in root of the directory and didn't add it
    to gitignore. I complained, and we agreed to parameterize the path
    and default to an ignored data/ folder in the project.
  - It hardcoded the schema and the queries. I asked it what was the
    proper way to manage schemas and migrations in Python and it
    suggested Alembic with SQLAlchemy, which I agreed to. The agent
    created the basic setup and I agreed to it without review, since I
    had already entered the zone where I have never really worked with
    the tools the agent was working with
  - In the middle of all this, I exceeded my quota for my Google Pro
    subscription, which I had only used for this project, and I had to
    wait a week to continue. It was supposed to be a 20€/month plan,
    but the first month was free, so maybe it has a lower quota.

- I asked the agent to define the initial schema. It came up with a
  proposal to which I agreed, and it implemented it. The agent
  suggested to do next the database session integration and the data
  models, and I told it to proceed.
  - For the models, the agent said it had wrote a test and run it for
    verification. But that test file wasn't commited and never reached
    the workspace either. I had to ask the agent to add it and commit
    it, and I'm not really sure that it didn't hallucinate it
    originally.

- I asked the agent for next step suggestions and it suggest to
  implement the basic commands one by one. It autonomously did so,
  without any review whatsoever of the code on my side. It added tests
  for all of them, but I didn't review them either, so who knows how
  good they are.
  - I had to remind the agent to update the documentation in the
    README for the new commands it was implementing or the new
    choices it was making for the original commands.

- The agent suggested as next action to write a dockerfile and
  document the deployment steps. I agreed and approved all the code
  without review

- I asked the agent to write for me a manual testing guide to test the
  progress so far
  - Most commands are not parsed correctly when you specify a user.
  - Otherwise, it mostly worked well

- I asked the agent to write this section, but didn't like the results
  so I wrote it manually

- I asked the agent where I should document the rules I want it to
  follow from now on in every new conversation. He suggested AGENTS.md
  and I asked it to write it with a few rules I came up with.

- I asked the agent to implement command autocompletion and it did
  successfully.

- I asked for suggestions about where to introduce inline buttons for
  the Telegram bot, and the agent suggested to start with the
  `/settle` command, the place I already had in mind. The agent
  implemented it but there were two issues:
  - The tests did not pass, but the agent fixed autonomously when I
    complained and shared the output (usually the agent runs the tests
    on its own, but in my last conversations the agent suddenly
    stopped being able to run them or run git commands, not sure why)
  - The feature did not work, but the agent also fixed it autonomously
    when I shared the error

- I asked to implement the second suggestion to add a `🗑️ Undo` button
  to `/pay` and `/payback` confirmations. It implemented it, I tested
  it, and it seems to work.

- I asked the agent to implement delete buttons when listing payments
  with /history and it did. It's not the way I had in mind, but it
  seems to work.

- I asked the agent to evaluate the project for quality standards. The
  agent proposed a few imporovements but not the basic one I had in
  mind, structuring the code property and moving the .py files to a
  src/ folder. I told it to do so and it did together with a few other
  related improvements.

- I asked about alternatives for hosting the bot since I couldn't run
  it on my laptop, using IaC as much as possible. The agent walked me
  through different approaches and providers, and we settled with a
  VPS (Infomaniak VPS Lite) using Ansible for automated
  deployment. The agent created the Ansible configuration, I signed up
  in Infomaniak and purchased the VPS, and deployed the bot following
  the agent instructions. After two errors which the agent fixed
  autonomously when I shared the `ansible-playbook` output, the bot
  was deployed successfully.

- I wanted to test how updates are propagated to the VPS and ensure that database
  history is preserved. The agent suggested updating the `/start` command response,
  which we did by adding a Joker quote. The test was successful.

- I wanted to test database schema migrations. The agent proposed to
  update the `Group` model with a new `created_at` column and I
  agreed. It was succesfull, the schema did change and the previous
  state wasn't lost

- I asked to add an "OK" button to parsing error messages to easily
  dismiss and delete them from the chat. The agent did it successfully.
  - I then asked to remove the original message too, and it also did
    it successfully, but it requires to promote the bot to admin

- I noticed a redundancy between pyproject.toml and
  requirements.txt. The agent explained the difference and, with my
  approval, removed requirements.txt and transitioned the setup
  (README, Dockerfile) to use pyproject.toml instead. It also fixed a
  unit test issue on the way.

- I noticed a redundancy between the Alembic migrations and models.py
  regarding the database schema definition. The agent explained to me
  that it's not an actual redundancy and that is the standard way to
  do it in Python, and I shouldn't compare to my known Java setup with
  JPA and Flyway.

- I asked the agent which files should be split and how to improve project structure. We decided to split `bot.py` into a modular package of handlers. The agent successfully moved all command and callback handlers into `src/heathen_ledger/handlers/` and refactored `bot.py` into a clean runner. It updated and ran the unit tests successfully.

- I asked for suggestions to make the `/pay` command easier to use. We settled on adding inline buttons to dynamically toggle participants in/out of the split. The agent implemented the `pay_toggle_callback_handler` and helpers, registered them, updated the message formatting, and added comprehensive unit tests which all passed.

- I asked to add support for sending commands through voice messages using an AI provider, and we agreed to start with Google Gemini while keeping the core agnostic to the provider. We agreed on an incremental phased plan:
  - In Phase 1, the agent implemented a voice/audio message handler echoing voice notes with duration and metadata to verify Telegram bot audio delivery and permissions.
  - In Phase 2, the agent added the Google Gemini SDK (`google-genai`), documented `GEMINI_API_KEY`, established a provider-agnostic `VoiceInterpreter` interface with a Gemini adapter skeleton, and added unit tests.
  - In Phase 3, the agent connected the voice handler with Gemini to download voice notes in memory, transcribe the audio, and interpret spoken intent into ledger commands with group member context, returning the transcription and proposed command. When testing, the user encountered that `gemini-2.5-flash` was restricted to new accounts; the agent updated the default model to `gemini-3.6-flash` and documented `GEMINI_MODEL`.

- I noticed that the bot was automatically processing every voice note sent to the chat and asked how we could let the user signal when an audio is intended for the bot. The agent presented multiple approaches (replying with a command/mention, captions, direct DM handling). I chose option 1 (replying to the voice note with a command or mention). The agent autonomously implemented reply detection for `/voice`, `/pay`, and bot mentions (`@bot_username`), added `/voice` to bot autocompletion and help text, updated tests, and updated the documentation. However, the agent had incorrectly claimed that replying to another user's voice message would work with Telegram Privacy Mode enabled; I corrected the agent that Telegram Privacy Mode strips `reply_to_message` unless Privacy Mode is disabled or the bot is an admin.

- I asked for a final design and specification for the `/pay` command so that an LLM can easily generate it from natural language, with support for reasons, amounts, optional dates, optional/multiple payers (joint accounts, couples, cash splits), and flexible split beneficiaries, while reserving overly complex split mechanisms (such as percentages, weights, and itemized receipts) exclusively for interactive Telegram UI elements like buttons and popups. The agent proposed a structured keyword-based grammar (`for`, `by`, `split`, `on`) with clean UI boundaries and an incremental implementation plan. I approved the design and instructed the agent not to worry about breaking backwards compatibility at this early development stage, but to design with future schema evolution in mind (using Alembic). The agent autonomously implemented the changes across the stack:
  - Created the `ExpensePayer` model and `expense_date` column on `Expense`, generating and running an Alembic migration (`add_expense_payers_and_expense_date`).
  - Updated CRUD operations and balance calculations to handle multiple payers and dates.
  - Implemented the advanced `/pay` parser with multi-payer, custom split, date, quoted description, and validation support.
  - Updated the bot expense handler and message formatting to record and display multi-payer contributions and dates.
  - Updated the Gemini voice interpreter system prompt with the new `/pay` specification, examples, and dynamic date context.
  - Added comprehensive unit tests across models, CRUD, parser, and handlers, and updated the documentation.

- I asked how user registration currently works, what data is saved, and whether the bot can work with users outside the Telegram group (e.g., people without Telegram). The agent explained the automatic registration handler, database schema constraints, and lack of external user support. I proposed adding a `/register` command to create external user profiles on the fly. The agent agreed and outlined a plan, which I approved. The agent autonomously:
  - Updated the `User` database model by making `telegram_id` nullable and introducing an `is_external` boolean flag, and generated/tested an Alembic migration (`add_external_users_support`).
  - Added CRUD helpers `create_external_user` and group-scoped user resolution (`get_user_in_group`) to safely find members within the active group and prevent cross-chat handle leaks.
  - Implemented `/register` (allowing `/register <name>` or `/register @handle <Display Name>`) and `/members` to view all group members.
  - Updated `/pay` and `/payback` to resolve external group members and updated `/settle` callback permissions so any registered member can confirm settlements when both parties are external.
  - Added unit tests for external user CRUD, bot commands, payments, and settlements, and updated the documentation.

- I asked to step back and evaluate code quality to make the code extensible for future iterations. The agent identified key improvement areas (decoupling handlers via a service layer, breaking up `parser.py`, replacing loose dictionaries with typed DTOs, configuration management, and audit tracking). I asked to start with the handler decoupling, parser modularization, and typed DTOs. The agent autonomously:
  - Extracted equal-split math and greedy debt simplification algorithms into `domain.calculations`.
  - Extracted presentation logic and Markdown summary generators into `formatters.py` with a reusable `format_cents` helper.
  - Introduced typed DTOs (`ParsedPayCommand`, `ParsedPaybackCommand`, `SplitSpec`, `ParseErrorResult`) with mapping backward-compatibility in `dto.py`.
  - Created a dedicated service layer (`ExpenseService` and `SettlementService`) in `heathen_ledger.services`, decoupling expense calculation, split toggling, paybacks, and settlements from Telegram `Update` handlers.
  - Added unit tests for the service layer and DTOs with all 81 tests passing.

- I asked to proceed with improving tests (reducing fixture boilerplate and modularizing test files). The agent autonomously:
  - Created `tests/base.py` with a reusable `BaseDatabaseTestCase` providing in-memory SQLite database setup, session patching, standard user/group fixtures, and Telegram mock update factory helpers.
  - Modularized `tests/test_bot.py` by breaking down the 692-line monolithic callback test suite into focused test classes (`TestSettleCallback`, `TestUndoCallback`, `TestHistoryDeleteCallback`, `TestDismissCallback`, `TestPayToggleCallback`, `TestPayCommandHandler`, `TestRegistrationHandlers`), cutting duplicate setup boilerplate by ~300 lines.
  - Migrated `tests/test_services.py` to inherit from `BaseDatabaseTestCase`. All 81 unit tests pass.

- I noticed the agent had to search for the `ruff` path and asked whether project verification and linting tools belong in a SKILL or `AGENTS.md`. The agent explained the difference between persistent workspace rules (`AGENTS.md`) and on-demand specialized workflows (skills). I asked the agent to update `AGENTS.md` with verification commands and a rule to automatically update `AGENTS.md` whenever an agent has to discover or validate project conventions. The agent updated `AGENTS.md` with environment commands (`.venv/bin/python`, `.venv/bin/pre-commit`, Alembic migrations) and a continuous knowledge capture rule.

- I asked why creating new files via shell redirection (`cat << 'EOF' > ...`) triggered manual approval prompts even though Antigravity is configured to allow file edits without review. The agent explained that shell commands are governed by the terminal execution policy rather than file modification permissions, and that Antigravity provides a native `write_to_file` tool that bypasses shell prompts. We updated `AGENTS.md` to mandate the use of native file creation tools (`write_to_file`) instead of shell redirection commands.

- I asked to improve user registration to make the bot compatible with Telegram Privacy Mode, specifically requesting: (1) `/register` with no parameters to create an inline button that members can touch to register, and (2) `/register` to work when mentioning a group member. The agent autonomously:
  - Added automatic profile linking in `crud.get_or_create_user`, allowing unlinked external/pending profiles to seamlessly upgrade and merge when a Telegram user registers by username.
  - Implemented `/register` with no parameters to send an interactive `[ 📝 Register me ]` inline button, along with a callback handler (`register:join`) that announces registrations and prevents duplicate entries while keeping the button available for other members.
  - Enhanced `/register` when mentioning members: supporting message replies (`reply_to_message`), text mentions (`TEXT_MENTION`), chat administrator lookups (`get_chat_administrators`), cross-group Telegram user lookups, and multi-user mentions (`/register @alice @bob`).
  - Updated bot command descriptions, help texts, test fixtures, and comprehensive unit tests (89 passing tests).

- I asked to implement the confirmation phase for audio commands, adding confirmation buttons so the user can execute or reject the command understood by the bot. The agent autonomously:
  - Added pending command state tracking with short tokens to comply with Telegram's 64-byte `callback_data` limit and prevent double execution or unauthorized confirmation.
  - Updated the voice audio processing pipeline to attach `[ ✅ Confirm ]` and `[ ❌ Reject ]` inline buttons to interpreted command responses.
  - Implemented `execute_voice_command` and `voice_callback_handler` to execute confirmed commands (`/pay`, `/payback`, `/balances`, `/settle`, `/history`) in the chat with full interactive button support (participant toggles, undo, debt settlements) or mark rejected commands without modifying the ledger.
  - Added comprehensive unit tests for confirmation, rejection, unauthorized click security, double clicks, and command execution across all supported commands (97 passing tests).

- I asked for a proof of concept for Telegram's ephemeral messages feature, requesting a test command which the bot answers with an ephemeral message. The agent researched Telegram Bot API 10.2 / 10.3 ephemeral message capabilities (`ephemeral_message_parameters` and `is_ephemeral` on `BotCommand`), verified `python-telegram-bot` 22.8 integration via `api_kwargs`, and autonomously:
  - Implemented the `/ephemeral` (and `/test_ephemeral`) command in `src/heathen_ledger/handlers/ephemeral.py`, targeting `receiver_user_id` in groups and providing friendly guidance and error fallback in private chats.
  - Registered the command handler and updated `post_init` in `bot.py` with `BotCommand("ephemeral", ..., api_kwargs={"is_ephemeral": True})` to enable two-way ephemeral commands in Telegram clients.
  - Documented `api_kwargs` usage for Bot API parameters in `AGENTS.md` and added `/ephemeral` to `/help` and `README.md`.
  - Added unit tests for group chats, supergroups, private chats, missing message/user edge cases, handler registration, and bot command registration (all 106 tests passing).

- I corrected the agent that the bot failed when replying to `/ephemeral` without administrator rights, pointing out the distinction in Telegram's documentation (https://core.telegram.org/bots/api#ephemeral-messages-and-commands): non-admin bots can only send ephemeral messages within 15 seconds if they provide `callback_query_id` from a button tap or `reply_parameters.ephemeral_message_id` from an incoming ephemeral command, whereas direct replies to regular commands require the bot to be a chat administrator. The agent autonomously:
  - Updated `src/heathen_ledger/handlers/ephemeral.py` to extract `ephemeral_message_id` from incoming messages for non-admin replies.
  - Added an inline button (`ephemeral_cb`) and callback query handler (`ephemeral_callback_handler`) demonstrating non-admin ephemeral responses via `callback_query_id`.
  - Updated error handling with clear explanations if a non-admin bot encounters permission errors on direct command invocations.
  - Documented the administrator and callback reply target conditions in `AGENTS.md` and `README.md`.
  - Added unit tests covering incoming `ephemeral_message_id`, callback query handling, and callback registration (all 110 tests passing).

- I asked for a different test focused specifically on ephemeral commands instead of an inline button. The agent autonomously:
  - Registered `/ephemeral` and `/whisper` with `api_kwargs={"is_ephemeral": True}` under `BotCommandScopeAllGroupChats` in `bot.py`, enabling Telegram clients to prompt and submit the command as an ephemeral invocation (`ephemeral_message_id`).
  - Updated `ephemeral_command` in `src/heathen_ledger/handlers/ephemeral.py` to remove the inline button dependency and directly answer with an ephemeral message, extracting `ephemeral_message_id` from `Mapping` proxies and message replies, and supplying `reply_parameters={"ephemeral_message_id": ...}` to satisfy Telegram's non-admin reply condition within 15 seconds.
  - Added diagnostic feedback displaying whether the command was received as ephemeral (two-way privacy active, non-admin allowed) or as a regular message (admin rights required).
  - Updated `tests/test_ephemeral.py` to mock `context.bot.send_message` and verify group, supergroup, and private chat behaviors (all 110 tests passing).
