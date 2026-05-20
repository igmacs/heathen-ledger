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
