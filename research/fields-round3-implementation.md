# Round 3 review follow-up

Base: `c2d9a05`, branch `codex/beginner-paper-explainer`. This follow-up preserves the existing offline explainer and nine-tool API.

## Findings

- Important1 — fixed. Each role retains up to four keyword candidates, with returned/omitted counts. Each candidate carries basis, original sentence number, source sentence, numeric tokens and candidate-only status. The challenge/95%-accuracy reproduction now retains both sentences. Missing numeric tokens mean detection or candidate coverage is incomplete, not that the abstract lacks metrics. Unmatched result phrasing also cannot establish absence. Numbers do not establish experimental validation.
- Important2 — fixed. `source_material` returns original supplied abstract/body text, with a total text budget of 16,384 Unicode code points, allocated abstract first and then original body paragraph order. Each item has original paragraph identity, half-open returned/omitted character ranges, original length, source URL where available, access note and next action. Full text within the budget is available in the same tool response. Beyond the budget the host must obtain the explicitly omitted range and submit it as userText; this API is stateless and does not offer hidden server-side retrieval or arbitrary full-paper copying. API abstract access never implies a full-paper license. Source content is explicitly untrusted data. Candidate source sentences additionally have a per-sentence 16,384-character cap and truncation flag (at most four per role); numeric tokens are extracted only from the returned sentence portion. These are bounded evidence locators, not translated scientific claims.
- Minor — fixed. Prose excerpts remove line-leading Markdown structure, remove inline formatting markers and collapse whitespace before the 96-character display limit. Structured source text preserves exact supplied Unicode content, including CRLF and paragraph positions; encoding it as UTF-8 preserves the supplied string's UTF-8 bytes. This is not a promise to recover an input file's unknown original encoding.

## TDD and validation

Each finding was tested separately before its implementation:

1. Important1 RED: three failures (missing multiple candidates, lost later metric, false absence claim); GREEN: 3 passed.
2. Important2 RED: two missing-source-material failures; GREEN: 5 cumulative passed.
3. Minor RED: multiline Markdown excerpt failure; GREEN: 6 cumulative passed.

Added a real MCP SDK stdio URL call with injected public-API transport (no live network): a method mechanism after character 96 survives in complete source material, with provenance. CLI JSON has identical evidence paragraphs and source text. The installed-wheel verifier also checks a long abstract through an actual SDK tool call.

Validation environment: existing `../.venvs/fields-study-flow/Scripts/python.exe` (Python 3.14). Default system Python 3.12 lacks MCP and failed collection; it is not the acceptance environment.

- Full pytest: 321 passed.
- Wheel: `pip wheel . --no-deps --no-build-isolation --no-index -w dist/round3`.
- Installed using `--no-index --no-deps --force-reinstall` into existing `build/round3-venv`; verifier runs from `build`, confirms site-packages import.
- Installed MCP: nine tools listed and all nine called successfully, plus long abstract source context check.
- Legacy JSONL: explicit compatibility flag, default server and git4study shim: 3/3 passed.
- CLI examples: abstract JSON and user-body prose: 2/2 passed.

No push, merge, paid service, live network fetch or delegated agent. Ignored build artifacts are retained; clean means no pending tracked/untracked Git changes after commit, not destructive `git clean -fdx`.
