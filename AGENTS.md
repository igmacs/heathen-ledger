# Workspace Agent Rules and Guidelines

Please follow these instructions and rules during all interactions in this workspace:

## 1. Incremental and Atomic Commits
* Write code incrementally and make small, focused commits.
* Commit after completing each logical file, bug fix, or small feature.
* Provide atomic and descriptive commit messages rather than batching multiple unrelated changes into a single large commit.

## 2. Document Interaction Changes
* Always document any changes that affect how the user needs to interact with the bot (e.g., changes to commands, parsing rules, database schemas, or deployment instructions).
* Keep the user-facing documentation (such as command listings or setup instructions in the `README.md`) up to date.

## 3. Maintain Agent Conversation History
* Keep the **Project evolution & Agent conversation history** section (at the end of `README.md`) up to date.
* For each session, append a summary of the progress made, decisions taken, where the agent was autonomous, and where the user had to correct or guide the agent.
* Use existing entries as reference for how brief those entries should be and what details are important and which ones aren't.

## 4. Environment & Verification Commands
* **Python virtual environment**: Always execute Python commands using `.venv/bin/python` (the system Python lacks project dependencies).
* **Testing**: Run the test suite with `.venv/bin/python -m unittest discover -s tests`.
* **Linting & formatting**: Run `.venv/bin/pre-commit run --all-files` (or `ruff check .` / `ruff format .`).
* **Pre-commit hooks**: Pre-commit hooks run automatically on `git commit`. If a hook (such as `ruff-format` or `end-of-file-fixer`) modifies files during commit, re-stage them (`git add`) and re-run the commit.
* **Database migrations**: Run Alembic migrations using `.venv/bin/alembic upgrade head`.

## 5. Continuous Knowledge Capture
* Whenever an agent has to guess, discover, or troubleshoot an undocumented project convention, tool path, environment quirk, or command, update `AGENTS.md` with the verified instruction so future agent sessions do not have to rediscover it.

## 6. File Creation and Editing Tools
* **Never use shell commands to create or write files**: Do not use `cat << 'EOF' > ...`, `echo ... > ...`, or `tee` via `run_command` to create new files or write code. Antigravity treats shell commands under its terminal execution policy, triggering manual approval prompts.
* **Always use native file tools**: Use `write_to_file` to create new files and `replace_file_content` to edit existing files. Because file editing is configured to auto-proceed, using native file tools avoids unnecessary approval interruptions.

## 7. Telegram Bot API Conventions
* **Ephemeral Messages & Bot API Parameters**: When using Telegram Bot API features (such as `ephemeral_message_parameters` on `sendMessage` or `is_ephemeral` on `BotCommand`) that do not have dedicated keyword parameters in `python-telegram-bot`, pass them via `api_kwargs` (e.g., `api_kwargs={"ephemeral_message_parameters": {"receiver_user_id": user_id}}` or `BotCommand(..., api_kwargs={"is_ephemeral": True})`). PTB merges `api_kwargs` directly into the outgoing request payload.
* **Ephemeral Messages Permissions & Reply Targets**: In group chats, Telegram requires the bot to be a **chat administrator** to send ephemeral messages directly in response to standard commands. Non-admin bots can only send ephemeral messages within 15 seconds if they provide either `callback_query_id` (from an inline button callback) or `reply_parameters.ephemeral_message_id` (replying to an incoming ephemeral message).
* **Incoming Ephemeral Message Inspection & PTB Specifics**: Incoming parameters not mapped directly to PTB model fields reside in `message.api_kwargs`, which is a `mappingproxy` (use `isinstance(api_kwargs, collections.abc.Mapping)` instead of `isinstance(api_kwargs, dict)`). Additionally, when replying to incoming ephemeral messages (where `message_id=0`), use `context.bot.send_message(chat_id=..., api_kwargs=...)` rather than `message.reply_text(...)`, as PTB's `reply_text` helper automatically injects `ReplyParameters(message_id=self.message_id)`.
* **Deleting & Editing Ephemeral Messages**: Ephemeral messages have `message_id=0` and **cannot** be deleted via standard `deleteMessage` / `query.message.delete()` or edited via standard `editMessageText`. Telegram Bot API requires dedicated methods: `deleteEphemeralMessage(chat_id, receiver_user_id, ephemeral_message_id)` and `editEphemeralMessageText(chat_id, receiver_user_id, ephemeral_message_id, text)`. In `python-telegram-bot`, call these via `bot._post('deleteEphemeralMessage', data=...)` and `bot._post('editEphemeralMessageText', data=...)`.
* **Rich Messages (Bot API 10.3+)**: Rich messages (`sendRichMessage`, `InputRichMessage`) support embedded buttons (`<tg-button type="callback_data" style="..." data="...">`) directly within message paragraphs/lines and tables rather than only below the message. Because `python-telegram-bot` (v22.8) does not yet have first-class classes for Rich Messages, use the `TelegramRichClient` adapter (`src/heathen_ledger/telegram/rich_client.py`) which wraps `bot._post('sendRichMessage', ...)`, `bot._post('editMessageText', ...)`, and `bot._post('editEphemeralMessageText', ...)` with fallback support for unit test mocks. When PTB adds native rich message models, replace only the internal adapter implementation in `rich_client.py`.
