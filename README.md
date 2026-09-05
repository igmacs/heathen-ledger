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
   - `/pay @Alice 50 for Dinner` (Alice paid $50.00; split equally among all members of the group chat).
   - `/pay @Alice 50 for @Bob @Charlie` (Alice paid $50.00; split specifically between Bob and Charlie).
   - `/pay 12.50 for Pizza` (The sender paid $12.50; split equally among all members of the group chat).
     - After recording an expense, the bot shows inline buttons for all group members. The creator of the expense can tap these buttons to dynamically toggle members in/out of the split, which automatically recalculates and updates the shares.

   > [!IMPORTANT]
   > **User Auto-Registration:**
   > To split an expense or specify a payer using their Telegram username (e.g. `@Alice`), that user **must have sent at least one message in the group** since the bot was added.
   > The bot auto-registers users when they send messages. If a user is mentioned but has never interacted, the bot will return a warning asking them to send a message to register.

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
   - Reply to the voice note with `/voice`, `/pay`, or tag the bot (`@HeathenLedgerBot`) to tell the bot that the audio is intended for it.
   - The bot transcribes the audio using Google Gemini and proposes the matching bot command (e.g. `/pay 25 for dinner`). Casual voice messages sent to the chat without a reply or mention are ignored.
   - *(Note: Interactive confirmation buttons to execute the proposed command will be enabled in Phase 4)*.

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

- I noticed that the bot was automatically processing every voice note sent to the chat and asked how we could let the user signal when an audio is intended for the bot. The agent presented multiple approaches (replying with a command/mention, captions, direct DM handling). I chose option 1 (replying to the voice note with a command or mention). The agent autonomously implemented reply detection for `/voice`, `/pay`, and bot mentions (`@bot_username`), added `/voice` to bot autocompletion and help text, updated tests, and updated the documentation.
