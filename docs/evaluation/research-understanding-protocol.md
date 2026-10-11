# Research understanding evaluation protocol

Protocol version: 1.0, 2026-10-10. **Status: proposed; recruitment and all human outcomes pending.** This document contains no participant observations, scores, time savings, or comparative wins. Freeze the protocol, materials, rubric, and budgets before recruitment; record any amendments with dates and reasons.

## Question and participants

Does a persistent, source-linked workbench help researchers explain and take over unfamiliar papers/project materials compared with a well-configured general agent using the same model and tools?

Recruit **8-12 target users** who read AI/CS papers or take over agent-produced research. Record research experience, language, topic familiarity, Python/mathematics background, prior exposure to each paper, and accessibility needs. Do not substitute maintainers or automated sessions for target users. This is an exploratory usability study, not a powered population-level effectiveness claim. Obtain consent, allow withdrawal, and separate participant identifiers/private notes from shareable artifacts.

## Conditions and fair baseline

| Condition | Access and task |
| --- | --- |
| A: direct model/agent, strong baseline | Full authorized input bundle, structured task prompt below, working file search/read tools, note export, and ordinary map/HTML generation tools if available. Permit clarification, navigation, source-cited explanations, and iterative correction; do not force a one-shot answer or deliberately weak prompt. |
| B: same model/agent plus fields-study-flow | Identical model version, system-level scientific accuracy requirements, input bundle, tools, token/request limits, and task. Workbench adds persisted anchors, material gaps, linked steps, and portable handoff. |
| C: optional native GPT/Claude/other product | Separate exploratory comparison only. Record product version/date, account tier, tools, memory, browsing, defaults, and all unavailable controls. Do not pool this with A/B or call it a same-model experiment. |

Before each paired session, freeze an explicit budget sheet: model provider and exact version; temperature and other settings; context/input/output token caps; maximum requests; available file/browser/code tools and invocation caps; allowed external sources; wall-time cap. Apply identical caps to A and B, including workbench explanation-generation calls, retries, and cache creation. Report actual usage and any overruns; never give B extra uncounted generation calls or A fewer file tools. If a component cannot be matched, label that comparison confounded and report it separately. Local deterministic parsing is logged as preprocessing, not a model call; both conditions may inspect every supplied file.

No live discovery for the controlled A/B comparison. Use frozen local bundles. With an authorized external explanation endpoint, both conditions use the same model; the public example generator remains entirely local and is not a study session. Log cold-cache generation and warm-cache reuse separately; do not hide B setup time by timing only the finished HTML.

### Baseline task prompt

> Using the supplied paper and project files, explain the problem, method, rationale, and limits in your own words. Cite exact source locations, distinguish author claims from interpretations, and identify unsupported conclusions or missing materials. For presentation, prepare a source-linked outline and likely questions. For handoff, locate the relevant implementation symbol, configuration, and existing results; propose one change and an observation that could test it. Do not invent missing files, measurements, or completed reproduction. Use available tools and revise your answer when evidence conflicts.

Adjust the goal clause identically in A and B to understand, present, or extend. Permit an experienced evaluator to improve the baseline prompt during pilot preparation, then freeze it before collecting outcomes.

## Materials and order

Use distinct, approximately matched bundles covering planning-paper, transformer-paper-project, and diffusion-missing-materials. Match task difficulty, supplied text length, source coverage, and project size as closely as feasible. Have a domain reviewer prepare a reference answer and record residual differences before testing.

Each user performs A and B on **different unfamiliar papers/materials**. Counterbalance condition order, topic assignment, and task goals across participants. Never have a user learn the same paper first in A and then in B and attribute the memory advantage to the tool. Record allocation and randomization seed before sessions. Give equivalent short familiarization on separate practice materials; exclude practice timings from study outcomes but report familiarization duration.

The three repository examples are demonstration/engineering fixtures, not automatically validated study materials. The Transformer toy is **our own demonstration, NOT an actual paper reproduction**; its hand-computed expected trace is not a measured paper result. The diffusion fixture intentionally lacks method/code/config/results. Missing-material detection can be tested there; full-method correctness cannot. Obtain appropriately licensed fuller materials for tasks that require them, preserve source version/hash, and do not invent an experiment to make a bundle look complete.

## Session and timing

1. Record background, unfamiliarity, goal, condition, allocation, input hashes, and budget sheet.
2. Start end-to-end timing at the first task/input handoff. Separately time ingestion, generation/waiting, active reading/interaction, independent assessment, and handoff/export. Record overlap so component totals do not double-count waiting.
3. Permit equivalent tool access and clarifications. Record interventions, crashes, unsupported answers, retries, missing materials, abandoned steps, and participant frustration without steering toward a preferred condition.
4. At the frozen cutoff, stop tool assistance. Ask the participant to explain independently and locate sources; use the same assessment questions/rubric in both conditions.
5. For extend tasks, identify a symbol, editable configuration, existing result locator, and a falsifiable next-change hypothesis. When required materials are absent, identifying that absence and the next acquisition/check is the correct outcome, not an automatic failure.
6. Export notes/answers/gaps, record usability comments and abandonment reasons, and verify whether another reviewer can follow the handoff. Optionally preregister delayed recall; otherwise do not claim retention.

## Measures and scoring

| Measure | Definition |
| --- | --- |
| Time to correct independent explanation | Time until the frozen rubric is met without live model help. Record non-completion as censored at cutoff, not a successful fast time. Report generation, active learning, and end-to-end time separately. |
| Explanation accuracy | Six criteria: problem, method mechanism, design rationale, experiment conditions, interpretation of evidence, and limitations. Score each 0 = wrong/unsupported, 1 = partial, 2 = accurate with relevant boundary. Mark unavailable criteria not assessable; never score absent material as known. |
| Source-location correctness | Correct inspected paragraph/page/symbol/line/config key/result row divided by required attempted locations. Also report requested, attempted, correct, missing, and stale counts; no credit for merely opening a file or producing an anchor ID. |
| Unsupported-conclusion detection | Correctly rejected claims with supporting reasons, plus missed unsupported claims and false alarms against supported claims. Reviewer-written challenge statements stay in assessment files and are labeled as challenges, not inserted as genuine results. |
| Modification-entry success | Correct symbol, configuration, relevant result locator or explicitly justified gap, plus a testable hypothesis and expected observation. Locating an entry is not implementing a change or reproducing the paper. |
| Handoff and burden | Reviewer followability, stale-source recheck, generation/wait time, interactions, actual tool/model usage and fees, abandonment, and blocker severity. |

Domain-informed reviewers freeze scoring examples and assess de-identified answers without condition labels where feasible. Record residual unblinding (e.g. recognizable formatting). Use a second reviewer for disagreements and report raw/independent scores and reconciliation. A source-location check verifies correspondence, not truth; automated coverage/readiness/model grades are not human understanding scores.

## Failures and reporting

Retain **all enrolled sessions**, including incomplete tasks, tool errors, parser omissions, bad candidate relations, unsupported explanations, wrong/stale anchors, exports that cannot be followed, and withdrawals according to consent. Distinguish participant dropout, infrastructure failure, and genuine task difficulty. Publish sanitized failure cases with input version, expected/actual behavior, attempted fix, and unresolved status, not only successful screenshots. Predetermine exclusions, show denominators and reasons, and never quietly replace a failed run.

Report per-participant and per-condition observations, paired differences, medians/ranges, all budget deviations, order/topic effects, reviewer uncertainty, and limitations. If uncertainty intervals or tests are used, state methods and small-sample limitations; do not infer population efficacy from 8-12 users. No preselected promotional improvement percentage. Keep automated engineering tests, visual/interaction checks, and human outcomes in separate sections.

Release gate: complete workflow and no unresolved blocking defect in tested scenarios. Better learning, speed, cost, retention, or exclusive capabilities may be advertised only when actual evidence supports them with scope and conditions.

## Pending result register

| Item | Current status | Evidence |
| --- | --- | --- |
| Recruitment / participant background | Pending | None |
| Frozen budgets, assignments, study materials and reference rubric | Pending | None |
| A/B sessions, timings and independent explanations | Pending | None |
| Reviewer scores and disagreements | Pending | None |
| Human failure cases and abandonment | Pending | None; not zero |
| Native-product comparison | Optional, pending | None |
| Comparative benefit / learning improvement | Not established | None |

Future anonymized session record fields: participant_id, condition, order, material_id/version/hash, goal, model/version/settings, budget and actual usage, setup/generation/active/assessment/end_to_end_times, answer artifact, source checks, unsupported-claim checks, modification/gap checks, independent reviewer scores, blockers, abandonment reason, exclusion reason, consent scope. Leave unknown values null/pending; do not fill illustrative rows with fabricated people or results.
