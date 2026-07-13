# apps/cli, local verification runner

Two entry points over `litmuz_core.run_pipeline`:

- `demo.py` - a scripted, offline demo (deterministic doubles, no network, no model).
- `verify.py` - the live runner against real PubMed, Crossref, PMC and the judge model.

## Demo (offline, no keys)

```bash
uv run python apps/cli/demo.py
```

It narrates four beats and asserts each one, so it exits non-zero if any guarantee slips: a
fabricated citation forced red, a mechanistic claim with no locatable support held yellow, a
safety-critical dose that can never auto-pass, and the judge model swapped by one config value.
The same assertions run in the gated suite (`packages/litmuz_core/tests/test_demo_script.py`).

## Live runner

```bash
uv sync                                 # once, installs the dev env incl. the model SDK
export ANTHROPIC_API_KEY=sk-ant-...      # required
export NCBI_API_KEY=...                  # optional, lifts NCBI rate limits

uv run python apps/cli/verify.py apps/cli/sample_memo.md
uv run python apps/cli/verify.py apps/cli/sample_memo.md --json   # full report JSON
cat my_memo.md | uv run python apps/cli/verify.py -               # read from stdin
```

## What the sample shows

The bundled `sample_memo.md` exercises the interesting behaviours:

- a normal cited claim about p53, checked against its reference and the retrieved evidence,
- a dosing claim ("5 mg once daily"), which the safety guard holds for a human even if the
  evidence supports it, so it never auto-passes,
- a claim citing PMID 99999999, which does not exist, so it is flagged as a fabricated
  citation without the judge ever being called.

Live results for the real citation depend on the actual PubMed record and the retrieved
text, so the exact verdict on the p53 claims may vary. The fabricated-citation and dosing
behaviours are deterministic.

## Notes

- Config knobs (judge model, thresholds, top_k, byte cap) are read from the environment by
  `Config.from_env()`; see `packages/litmuz_core/src/litmuz_core/config.py`.
- This is a developer tool. The hosted surfaces are the REST API (`apps/api`), the worker
  (`apps/worker`), the MCP server (`apps/mcp`) and the web app (`apps/web`).
