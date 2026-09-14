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
