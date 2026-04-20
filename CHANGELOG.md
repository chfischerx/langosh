# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and a GitHub pull-request
  template — brings the repo to 100% on GitHub's Community Standards.
- `SECURITY.md` — explicit threat model, reporting channel, and
  callouts for the prompt-injection / auto-approve risk surface.
- `.github/dependabot.yml` — weekly `pip` + `github-actions` update
  PRs, grouped by ecosystem (LangChain / provider SDKs).
- `.github/CODEOWNERS` and `.editorconfig` — auto-request reviews
  from the maintainer; consistent indentation across editors.

### Changed

- README chapter **Works with LangGraph Platform / LangSmith**
  rewritten around the "Langosh is a dev tool; the LangGraph client
  is scoped to testing + diagnostics" framing. Points at
  [`docs/langgraph_api.md`](docs/langgraph_api.md) for the full
  endpoint-to-command map.

## [0.1.1] — 2026-04-20

### Added

- LICENSE file (MIT) committed at the repo root.
- Full PyPI metadata in `pyproject.toml` — `readme`, `license`
  (PEP 639), `authors`, `keywords`, Python 3.11 / 3.12 / 3.13
  classifiers, and a `[project.urls]` block pointing at langosh.ai,
  the GitHub repo, issues, and changelog.
- Landing page at [`langosh.ai`](https://langosh.ai) with the
  Google-Analytics snippet inlined so the standalone page rolls up
  into the same property as the Jekyll-rendered Markdown docs.
- GitHub badges in README (PyPI version + Python versions, plus
  GitHub license / issues / stars / CI / Publish — the latter four
  render once the repo is public).

### Fixed

- Lint cleanup — CI goes green: `ruff --fix` sweep (imports,
  unused imports, f-string clean-up), line-length bumped to 120,
  per-file E501 ignore on LLM-facing prompt files, removed two
  lingering `F401` imports.
- `docs.yml` build source set to `./docs` so `docs/index.html`
  becomes the site root instead of auto-rendering the root
  `README.md`.

## [0.1.0] — 2026-04-19

Initial public release.

### Added

- **Graph authoring:** `/initrepo` scaffold, `/graphs /create`
  conversational builder, `/compile` JSON → Python codegen, per-graph
  builder history persisted in the agents repo.
- **Tool catalog:** build-time discovery of
  `langchain_community.tools` + `langchain_experimental.tools`
  (~70 tools), cached per agents-path, surfaced to the builder LLM.
- **LangGraph client** (`server_client.py`) covering assistants,
  threads, runs, streaming, and history — enough surface to drive
  `/test` and `/run` with configurable `stream_mode`.
- **`/chat` and `/code` modes** with streaming across Anthropic,
  OpenAI-compatible, AWS Bedrock, and the Claude Agent SDK.
- **Mode tree UX** — hierarchical `/graphs /exec /server /settings`
  modes, a persistent input widget with background worker, sub-mode
  cycling (`/plan`, `/auto`, `/edit`).
- **CI + publish** workflows (`ruff` lint, Python 3.11 / 3.12 /
  3.13 matrix, PyPI trusted publishing on tag).

[Unreleased]: https://github.com/chfischerx/langosh/compare/v0.1.1...HEAD
[0.1.1]: https://github.com/chfischerx/langosh/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/chfischerx/langosh/releases/tag/v0.1.0
