# Turn on Claude

Reading unknown bills, proposing a contract's terms and answering questions about documents are
built (`house_cost/claude.py`) but off until an Anthropic API key is set.

- Decide whether to use it: with a key, the bill or document being read is sent to Anthropic's API.
- On the server: set `ANTHROPIC_API_KEY` (or `ANTHROPIC_API_KEY_FILE` from a Docker secret) in
  the deployment's `docker-compose.yml`; `CLAUDE_MODEL` defaults to `claude-opus-5-5`.
- Never exercised against the real API: tests use a stand-in for it. Try each feature once with a
  real bill and contract after turning it on.
