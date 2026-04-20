# Security Policy

## Supported Versions

Langosh is currently in active development. Only the latest published
version on PyPI receives security fixes.

| Version | Supported |
| ------- | --------- |
| Latest  | ✅ Yes    |
| Older   | ❌ No     |

## Reporting a Vulnerability

**Please do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately using [GitHub's private security
advisory feature](https://github.com/chfischerx/langosh/security/advisories/new).

Alternatively, you can reach the maintainer directly — contact
details are on the [langosh.ai](https://langosh.ai) website.

### What to include

A useful report typically contains:

- A clear description of the vulnerability and its potential impact
- Steps to reproduce (Langosh version, Python version, relevant
  `definition.json` / prompt, exact commands used)
- The affected component (e.g. codegen, tool dispatcher, editor
  auto-approve flow, history store, scaffold)
- Any suggested fix or mitigation, if you have one

### What to expect

- **Acknowledgement** within 48 hours
- **Status update** within 7 days (confirmed, not reproducible, or
  working on a fix)
- A fix released as soon as practical, typically within 30 days for
  critical issues
- Credit in the release notes if you'd like it

## Threat model

Langosh is a **local developer CLI**. The intended threat model
assumes it runs on the developer's workstation, reads/writes an
agents repo they own, and talks to LLM providers + LangGraph servers
they've configured themselves. It is not a service, does not accept
remote requests, and stores no secrets of anyone except the user.

Reports are most valuable for:

- **Prompt-injection → code execution** — a malicious tool result,
  fetched doc page, or adversarial `definition.json` causing the
  builder to emit Python that the compiler loads (the codegen
  verification step imports the generated module).
- **Prompt-injection → shell / filesystem abuse** in `/code` mode
  when `edit` sub-mode (auto-approve) is active.
- **Credential leakage** — API keys accidentally persisted in the
  cached conversation history (`.langosh/chat.json`,
  `graphs/<id>/.history.json`), tool-catalog cache
  (`~/.langosh/tools_cache/`), or the Langosh debug store.
- **Path traversal** — scaffold writes, graph compilation, or
  editor tools escaping the agents-repo root.
- **Supply-chain** — unexpected code execution triggered at
  `/fetchtools` when walking `langchain_community.tools` /
  `langchain_experimental.tools` import chains.
- **Transport** — any leakage of LLM-provider keys, LangSmith
  tokens, or `.env` contents to unintended destinations.

Out of scope:

- Vulnerabilities in upstream dependencies (LangChain, LangGraph,
  provider SDKs, prompt_toolkit, etc.) unless exploitable **through**
  Langosh's surface — report those to their maintainers.
- Anything that requires attacker-controlled access to the user's
  shell, home directory, or `~/.langosh/` state.
- Prompt outputs that are merely undesirable (bias, hallucinations,
  low-quality graphs) — these belong in issues / feature requests.
- Risks from deliberately running a third-party `definition.json`
  the user has not reviewed: that's equivalent to running untrusted
  code.
- The LLM providers' or LangGraph server's own security boundaries.

## Notes on the auto-approve sub-modes

`/code /edit` and `/graphs /select <id> /edit` skip per-tool
approval prompts. This is intentional for ergonomic iteration, but
increases blast radius if prompt injection slips through. For
untrusted prompts or untrusted repos, stay in `/plan` (read-only) or
`/auto` (per-tool approval). See the [Langosh README](README.md#universal-commands)
for mode details.

If you find a way for prompt injection to escalate past these
guards — especially out of `/auto` — that's a high-priority report.
