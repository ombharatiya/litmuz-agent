# Litmuz

**A claim-level verification layer for life-sciences research agents.**

Paste an AI agent's research memo. Litmuz breaks it into atomic claims, checks each claim's
citations against the primary literature, retrieves evidence, judges entailment with Claude,
applies a safety gate, and returns an auditable, per-claim traffic-light verdict:

- 🟢 **green — grounded**: supported by evidence, with a clean, resolvable citation.
- 🟡 **yellow — needs review**: unverifiable, unsupported, or safety-critical. Never a pass.
- 🔴 **red — flagged**: contradicted by the evidence, or the citation is fabricated.

Litmuz is built on one principle — **honest negatives**. It never dresses an unsupported
claim as a pass, and safety-critical claims (a dose, an indication, a molecular target) never
auto-pass, no matter how confident the model is.

---

## The problem

AI research agents are fluent, fast, and confidently wrong in ways that are expensive in the
life sciences. They cite papers that don't exist, cite real papers that don't actually support
the claim, and state doses or indications with the same certainty as a well-grounded fact. A
reader cannot tell a grounded claim from a fabricated one by looking at the prose. In a domain
where an unsupported dosing claim can cause real harm, "sounds right" is not good enough.

Litmuz sits between the agent and the reader as a verification layer: it re-derives, claim by
claim, whether what the agent wrote is actually supported by the literature it points to — and
says so plainly when it is not.

## How it works

The pipeline (`packages/litmuz_core`) runs six stages. The one importable core is called
identically by the REST, worker, and MCP surfaces, so an MCP tool call and a web submission
produce the same verdict.

```
memo
  │
  ▼
1. DECOMPOSE ───────────  split body from references (deterministic); Claude extracts atomic
                          factual claims as verbatim substrings; in-text citation markers are
                          resolved to concrete identifiers (PMID / DOI / PMCID). Gaps in the
                          memo are reported as "unclaimed spans".
  │
  ▼
2. CITATION CHECK ──────  deterministic, NO LLM. Each identifier is resolved against
                          authoritative metadata (PubMed / Crossref / PMC). Outcome is one of
                          ok · metadata_mismatch · fabricated · unresolved · unknown, plus the
                          source's retraction posture (active · retracted · expression-of-concern).
                          Title / author / year are matched against the record.
  │
  ▼
3. RETRIEVE ────────────  pull evidence passages: open-access full text (PMC BioC), cited
                          abstracts (PubMed E-utilities), or a keyword search for uncited claims.
  │
  ▼
4. ENTAILMENT JUDGE ────  Claude, one claim × one passage per call. It may answer only
                          supported / contradicted / unsupported, and must quote one verbatim
                          sentence from the passage as evidence. Bounded retries; a passage that
                          never parses becomes a judge_error, never an exception. Per-passage
                          results fold worst-case (contradicted > supported > unsupported).
  │
  ▼
5. SAFETY GATE + SEVERITY  deterministic, NO LLM, a pure function. Verdict + citation state map
                          to a diagnostic (D1–D5), a traffic light, and routing flags. Two
                          independent gates guard the green light (see below).
  │
  ▼
6. REPORT ──────────────  an auditable per-claim record: traffic light, diagnostic, verdict +
                          confidence, the verbatim evidence sentence and its source, every
                          citation check, category, and whether a human needs to look. Persisted
                          append-only.
```
### Verification Flow

<img width="1512" height="982" alt="Screenshot 2026-07-14 at 6 27 34 AM" src="https://github.com/user-attachments/assets/4060ff1f-8190-4701-b759-56ea2c07fb5c" />

### Human Review

<img width="1512" height="982" alt="Screenshot 2026-07-14 at 6 27 39 AM" src="https://github.com/user-attachments/assets/6ee2f567-a772-4426-994a-2e6a04e276a6" />


### The two guarantees

**Honest negatives.** A claim is green only when the evidence genuinely supports it and the
citation resolves cleanly. Yellow and red are never quietly upgraded, and the UI is held to the
same rule: a non-green claim can never render with the "grounded" colour or the check icon
(there is an end-to-end test that asserts exactly this). A fabricated citation forces red
*without the judge ever being called*.

**The safety gate.** Safety-critical claims can never auto-pass. Crucially, safety-criticality
is re-derived at the severity stage by an independent deterministic lexical oracle
(`safety.py`) — a dose, a dosing regimen, an indication, or a molecular target — so the cap
never rests on the model's own category label. High recall is deliberate: a false positive only
over-routes a claim to a human. A retracted source or an expression of concern can likewise
never be green.

**Human review is the only thing above the rubric.** A reviewer can resolve a flagged claim; a
human's final label (supported / contradicted / unsupported) re-derives the claim's light and
is recorded with who decided it. This is the one authority allowed to promote a claim the
pipeline itself would never auto-pass.

### Deterministic and model-agnostic by construction

Every threshold, label, and model id lives in one `Config` (`config.py`); no status string or
number is hard-coded elsewhere. The deterministic stages (citation check, severity/safety) are
pure functions — same inputs, same output, every time — and the judge model is swappable with a
single config value (it defaults to `claude-opus-4-8`). The stages that do call a model
(decompose, judge, categorize) depend only on an `LlmClient` protocol, so tests inject a
deterministic fake and never touch the network or a model.

### Prompt-injection defence

The memo and every retrieved passage are untrusted text. Before they reach the model they are
wrapped in fenced blocks tagged with a fresh, unguessable per-call token
(`prompt_safety.py`), and the system prompt instructs the model to treat everything inside the
fence as data only — so a claim or a fetched abstract cannot smuggle in instructions.

## The MCP server

`apps/mcp` ships an [MCP](https://modelcontextprotocol.io) server so **any Claude-powered agent
can call verification as a tool** — over stdio for local development and Streamable HTTP for
hosting. It exposes four tools:

| Tool | What it does |
| --- | --- |
| `verify_output` | Submit an agent memo for verification; returns a `job_id` to poll. |
| `verify_claim` | Verify a single claim synchronously; returns the verdict and `requires_human_review`. |
| `get_job_status` | Status and per-stage progress of a verification job. |
| `get_provenance` | Fetch a stored provenance report by id (owner-only). |

The tools carry no logic of their own — they call the same `litmuz_core` pipeline as the web
app, so an agent that self-checks through the MCP gets exactly the verdict a human would see in
the UI. Caller-supplied sources are treated as additive evidence: they never suppress the
deterministic citation check or the safety cap.

## Monorepo architecture

A `uv` workspace of framework-free core packages with thin adapters around them.

```
packages/
  litmuz_core      the verification pipeline — decompose · cite · retrieve · judge ·
                   categorize · severity/safety · report — plus schemas, config, and
                   prompt-safety. No web, queue, or database dependencies.
  litmuz_store     PostgreSQL persistence: numbered SQL migrations, least-privilege roles,
                   and append-only provenance enforced by GRANTs.
  litmuz_service   application service: submit and run jobs, weekly quota, and a Queue
                   abstraction (InMemoryQueue for dev/tests, SqsQueue for hosting).
apps/
  api              FastAPI REST adapter (submit / poll / report / review queue).
  worker           async queue-consuming worker that runs the pipeline off the request path.
  mcp              the MCP server described above.
  cli              a local runner: an offline, no-network demo and a live runner against real
                   PubMed / Crossref / PMC and the judge model.
  web              a Next.js UI: composer, live progress, the per-claim report, and a
                   reviewer queue.
infra/
  migrations       the hand-written, idempotent SQL schema migrations.
```

## Trying it locally

The fastest way to see the guarantees is the offline CLI demo — deterministic doubles, no
network, no model, no keys:

```bash
uv sync
uv run python apps/cli/demo.py
```

It narrates and asserts four behaviours: a fabricated citation forced red, a mechanistic claim
with no locatable support held yellow, a safety-critical dose that can never auto-pass, and the
judge model swapped by a single config value. To run against the real literature and the judge
model, see `apps/cli/README.md` (needs `ANTHROPIC_API_KEY`; the database-backed API, worker,
and MCP surfaces additionally need PostgreSQL).

## Built with Claude

Built for the **Built with Claude: Life Sciences** hackathon. Claude does the language-level
work in the pipeline — decomposing a memo into atomic claims, judging one-claim-against-one-
passage entailment, and categorizing claims — while every consequential gate (citation
resolution, the safety cap, the traffic-light mapping) is deterministic and model-free, so the
verdict is auditable and the negatives stay honest.

## License

MIT — see [LICENSE](LICENSE).
