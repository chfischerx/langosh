## Summary

<!-- What does this PR do? One or two sentences, imperative mood. -->

## Motivation

<!-- Why is this change needed? Link issues with "Fixes #123" or
     "Refs #123" if applicable. -->

## Testing

<!-- How did you verify this works? Commands run, manual steps,
     new tests added. -->

- [ ] `ruff check src/` is clean
- [ ] `pytest -q` passes (if tests exist)
- [ ] `langosh version` still works after `pip install -e .`

## Checklist

- [ ] PR title is short and in imperative mood
- [ ] Relevant docs are updated (`README.md`, `docs/langgraph_api.md`,
      scaffold templates in `src/langosh/init_repo.py`, etc.)
- [ ] No new dependencies added without discussion in the PR body
- [ ] No secrets or tokens in the diff
