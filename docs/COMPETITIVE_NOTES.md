# Competitive Notes

fields-study-flow is designed to sit between full tutoring platforms and one-shot prompt libraries.

## Observed Gaps in Similar Projects

- Generic learning path generators often produce plausible text but do not keep a source registry, learner profile, or resource scoring trace.
- Tutor platforms are powerful but heavy to deploy and less portable across agent environments.
- Awesome lists collect links but do not adapt to a learner's knowledge state or target outcome.
- Video/community resources are useful for intuition, but most tools fail to distinguish them from primary papers, official docs, and maintained code.

## Product Wedges

- Agent-native distribution through skills plus MCP tools.
- AI/CS taxonomy and learner profile as first-class data.
- Language-independent route generation with separate resource language preference.
- GitHub as a learning source, not just a code source.
- Explicit source policy that avoids piracy, login bypass, and video downloading.

## 2026 Competitor Scan and Product Implications

This scan focuses on products that overlap with fields-study-flow's goal: helping a learner turn papers, references, and local files into understanding.

Source refresh on 2026-06-22:

- Elicit emphasizes large academic search, customizable research reports, systematic-review support, and sentence-level citations: https://elicit.com/
- SciSpace positions itself as a citation-backed research agent with Chat with PDF, literature review, topic finding, and data extraction tools: https://scispace.com/
- NotebookLM positions itself as an AI research and thinking partner that turns uploaded sources into summaries, answers, audio-style overviews, and other study artifacts: https://notebooklm.google/
- ResearchRabbit emphasizes quick organized literature exploration and visual expansion from one paper to related works, authors, and emerging topics: https://www.researchrabbit.ai/
- get-it frames the wedge as turning a PDF into a measurable mastery map built around the document: https://github.com/beltromatti/get-it
- roadmap.sh keeps the first interaction simple through clear role/skill roadmaps and guided learning paths: https://roadmap.sh/
- React Flow remains the pragmatic canvas layer for pan, zoom, drag, minimap, whiteboard, and mind-map style interactions: https://reactflow.dev/

| Product / Project | What it is strong at | Gap for mastery learning | Product implication for fields-study-flow |
| --- | --- | --- | --- |
| Elicit | Large-scale scientific search, customizable research reports, systematic-review workflows, libraries, alerts, and sentence-level evidence support. | It is optimized for evidence-based research workflows, not for proving that one learner can explain, derive, reproduce, and critique a target paper. | Keep evidence citations, but turn them into a shortest mastery route and explicit validation tasks. |
| SciSpace | Research-agent surface with citation-backed results, Chat with PDF, literature review, writing, topic finding, and data extraction tools. | It is broad and assistant-like; the user can still leave without a concrete route, local asset bundle, or artifact checklist. | Keep the UI direct: one start page, then Paper Map, Paper Lens, and roadmap checklist. |
| NotebookLM | Source-grounded study companion that turns uploaded material into summaries, explanations, and portable study outputs. | Its outputs are helpful, but they are not automatically a mastery contract for explaining, deriving, reproducing, and critiquing a specific paper. | Require portable study outputs in our release gate: presentation notes, concise reading exports, and mastery artifacts. |
| ResearchRabbit | Visual literature exploration from one paper into related works, authors, and emerging topics; strong organization and topic-level visualization. | It answers "what else is connected?" better than "what should I learn first, and when am I done?" | Use graph interfaces for understanding, but keep the central chain tied to the target paper's logic. |
| Litmaps | Discovery, bird's-eye visualization, sharing, monitoring, and broad related-work coverage. | It is excellent for literature discovery, but the map is not automatically a learning path with evidence and tasks. | Treat literature maps as resource discovery, then filter resources by whether they shorten the learning path. |
| get-it | PDF-centered "measurable mastery map" idea with a strong focus on the document itself rather than a generic summary. | It is closer to single-document study; fields, courses, resource download management, and paper logic extraction can still differentiate. | Keep the target paper at the center and make mastery evidence visible. |
| roadmap.sh / developer-roadmap | Clickable learning nodes, beginner-friendly paths, and a very clear first interaction. | Generic roadmaps are not generated from a specific target paper and do not bind every step to evidence. | Use the "click a node, read what matters" interaction model, but generate nodes from paper metadata, RAG evidence, and selected resources. |
| React Flow / xyflow | Mature node canvas primitives: node dragging, zooming, minimap, keyboard accessibility, layout examples, and whiteboard interactions. | It is infrastructure, not a study product. | Continue moving Paper Map from static cards toward a polished canvas, while preserving offline single-file export. |

## Product Moves Already Landed

- A zero-setup `fields-study-flow demo` command now generates a complete Transformer-paper sample report, so new users can evaluate the product before preparing their own PDF or resource folder.
- `fields-study-flow demo --market-check` now turns that sample into a one-command product check, writing `demo_market_check.json` and `release_readiness.html` so reviewers can see whether the demo is market-ready or which evidence gates remain missing.
- A folder-level `index.html` now gives a single "start here" entry, reducing the number of choices a new user faces after export.
- The start page now includes "bring your own paper" command templates for both public URLs and local PDFs, converting a demo viewer into a real user workflow.
- The start page now includes a "10-minute quickstart" panel for one-paper reports, copying the low-friction "get started" feel of interactive roadmap products while keeping the flow paper-centered: map first, paragraph reading second, mastery evidence last.
- The start page now includes an intent router for "fastest understanding", "presentation-ready", and "validation/reproduction" modes, reducing first-click ambiguity for learners who do not yet know the report structure.
- The start page now includes three starter questions plus `fields-study-flow ask` commands, borrowing NotebookLM-style guided learning while keeping every question tied to local bundle evidence and mastery artifacts.
- The start page now includes a 5-minute active-recall self-check with expandable cards, adapting NotebookLM/Scholarcy/Get It flashcard lessons into evidence-seeking prompts rather than detached quiz trivia.
- Exports now include `study_cards.md`, a portable active-recall card set generated from the same prompts as the start page, so NotebookLM-style study cards become a local artifact instead of an online-only interaction.
- Exports now also include `study_quiz.md`, an evidence-linked self-graded quiz with an answer key, turning NotebookLM-style quizzes into a local mastery check instead of another passive summary.
- Exports now include `quick_brief.md`, a one-page first-read brief that adapts Scholarcy-style quick summaries and Spotlight key findings into a paper-logic chain with evidence links and next actions.
- Exports now include `evidence_coverage.md` and `evidence_coverage.html`, a portable evidence coverage matrix and readable dashboard that adapt Elicit-style citation transparency into a learner-facing audit of which Paper Map claims, Paper Lens paragraphs, mastery tasks, and resources are actually source-backed.
- The evidence coverage matrix now reports clickable source diagnostics, a measured coverage score, per-surface scores, and a prioritized evidence-gap queue, turning ResearchRabbit/Litmaps-style orientation into an actionable "what evidence should I fix first?" checklist.
- The evidence coverage matrix now also includes an explain/derive/reproduce/critique mastery-readiness scorecard, adapting NotebookLM-style active learning outputs into a stricter local mastery contract: the learner can see whether every core gate is ready, missing evidence, or missing a task.
- The start page now includes a 45-60 minute first-session plan, combining roadmap.sh-style low-friction pathing with NotebookLM/Get It-style active study outputs: map the paper, read one evidence paragraph, recall from memory, and finish one checkable mastery task.
- The start page now uses action-first progressive disclosure: secondary value explanation, report-health checks, alternate guidance, and bring-your-own-paper commands stay collapsed until the learner asks for them, keeping the first view closer to roadmap.sh's simple first interaction.
- Single-paper reports prioritize `paper_map.html` first, because the fastest way to understand a paper is to see the logic chain before reading every paragraph.
- Paper Map now exposes an adaptive reading-density control: beginners start in "core chain" mode, while advanced users can switch to the full evidence/resource/task exploration view.
- Paper Map now exports the causal logic chain as a downloadable Markdown presentation script, so "understand the paper" can become a short oral report without manual copying.
- `paper_lens.html` is paragraph-based rather than sentence-fragment based, making explanations lighter and less repetitive.
- `roadmap.html` contains a mastery checklist so the route does not end at "read these links".
- The roadmap mastery checklist now copies or downloads a `mastery_worksheet.md` evidence log, so progress can leave the browser and become a reviewable artifact.
- `roadmap.html` resource rows now show purpose badges and "why read" hints, so learners can distinguish primary evidence, background, implementation/reproduction help, and validation materials at a glance.
- `roadmap.html` resource rows now also show strength/provenance signals and their visible basis, distinguishing core resources, recommended supplements, and manual fallbacks with local availability, evidence score, trust score, recommendation score, recommendation reasons, source provenance, and paper-logic/learning-surface coverage when available.
- `roadmap.html` resource rows now surface the strongest available evidence snippet from RAG/resource metadata, bringing Elicit/SciSpace-style citation transparency into the local study bundle.
- The strongest resource evidence now links back to Paper Lens anchors, downloaded local files, or original sources when available, so learners can click from a recommendation to the exact evidence trail instead of trusting a detached summary.
- `fields-study-flow audit-report` now provides a local quality gate for exported HTML, checking privacy redaction, responsive metadata, wrapping safeguards, width constraints, font stacks, and key report affordances.
- `report_audit.json` now includes a market-readiness score across onboarding, visual polish, learning depth, plain explanations, resource completeness, and mastery actionability, turning competitor-derived product criteria into an executable quality gate.
- `report_audit.json` now also includes `experience_risks`, which checks discoverable quickstart guidance, the first-session plan, secondary-guidance progressive disclosure, intent-based entry choice, real Paper Map canvas affordances, branch deferral, paragraph-focused reading, local-first resources, and mobile/long-text layout safety.
- `report_audit.json` now includes `fresh_user_flow`, a first-10-minutes gate that checks whether a new learner can move from the start page to Paper Map, Paper Lens, local resources, and the first mastery task without hunting through the report.
- `report_audit.json` now includes `viewport_risks`, a lightweight desktop/mobile layout budget that checks responsive breakpoints, long-text wrapping, Paper Map canvas height, and mobile-safe resource lists before a report can be treated as market-ready.
- `report_audit.json` now includes `visual_snapshot_matrix`, a static screenshot-proxy matrix for desktop/mobile plus long-title, dense-resource, and dense-Paper-Map stress scenarios. This catches reports that technically have the right features but would look cramped or fragile in real viewing contexts.
- `fields-study-flow audit-report --capture-screenshots` now adds optional browser-backed desktop/mobile screenshot capture after `python -m pip install -e ".[visual]"` and `python -m playwright install chromium`. It writes `visual-snapshots/manifest.json` with relative paths when Playwright/Chromium is available and reports a clear skipped status when the optional browser runtime is missing.
- `fields-study-flow audit-report --probe-interactions` now adds optional browser-backed interaction smoke tests for Paper Map branch expansion, node detail updates, zoom/pan behavior, Paper Lens paragraph selection, and roadmap resource filtering. Release readiness no longer treats static markers alone as proof that the report is usable.
- `fields-study-flow audit-report --snapshot-baseline path/to/manifest.json` now compares current screenshot metadata against saved golden baselines, including required pages, desktop/mobile viewports, dimensions, and screenshot hashes.
- `fields-study-flow audit-report --fresh-user-minutes N` now records a measured fresh-user run from opening `index.html` to reaching the first mastery task. The default target is 10 minutes, and exceeding it makes the audit command fail.
- `fields-study-flow audit-report --write-fresh-user-worksheet` now writes `fresh_user_test.md`, a manual first-run usability worksheet for recording checkpoints, blockers, confusion, and product fix ideas.
- `fields-study-flow audit-report --fresh-user-worksheet-input <worksheet-path> --write-fresh-user-backlog` now aggregates completed worksheets into `fresh_user_backlog.md`, ranking repeated onboarding blockers first and redacting private local paths.
- `fields-study-flow audit-report --fresh-user-backlog-input <backlog-path> --write-fresh-user-trend-report` now aggregates backlog files into `fresh_user_trends.md`, highlighting blockers that recur across releases or report variants.
- `fields-study-flow audit-report --write-release-readiness` now writes `release_readiness.md` and `release_readiness.html`, combining market readiness, visual QA, screenshot/baseline status, browser interaction probes, fresh-user timing, recurring blockers, and competitor-inspired gates into a single release decision dashboard. A report cannot be marked `ship` without measured fresh-user timing plus real visual and interaction evidence.
- When the release-readiness dashboard is written, `index.html` now receives a single idempotent "Release decision / 发布决策" entry so reviewers can find the ship / needs_work / do_not_ship verdict from the report's start page.
- `fields-study-flow audit-report --write-release-history` now writes `release_readiness_history.jsonl`, `release_readiness_history.md`, and `release_readiness_history.html`, a sanitized cross-run log with trend, score-delta, and recurring-blocker-delta summaries for comparing release decisions, timing, blockers, and report links across versions. The start page and release-readiness dashboard get quality-trend entries so non-technical reviewers can find the dashboard.
- `audit-report` now adds `generated_artifact_audit` whenever it writes release dashboards, so newly generated HTML pages are checked for privacy, viewport, wrapping, font, encoding, and decorative-ellipsis risks before the command exits.
- `report_audit.json` now includes `competitive_benchmark`, which converts the competitor scan into explicit checks: PaperQA/PaperQA2-style grounded evidence, Explainpaper-style contextual explanations, Scholarcy-style structured review cards, Get It-style measurable mastery maps, roadmap.sh-style first interaction, React Flow-style canvas affordances, Litmaps/ResearchRabbit-style research-context boundaries, resource purpose badges, resource strength/provenance/coverage signals, clickable resource evidence review links, and local-first study bundles. A report cannot be marked market-ready while this benchmark warns.
- The same benchmark now checks NotebookLM-style portable study outputs: a single-paper report should expose at least two usable outputs such as presentation notes, a PDF/LaTeX reading export, or concrete mastery artifacts.
- Exports now write `mastery_worksheet.md` as a fillable evidence log, so the Get It-style mastery contract leaves the browser and can be reviewed, submitted, or pasted into a lab notebook.
- The local study bundle `README.md` is now a first-use dashboard with completion rate, a 10-minute start path, route/supplemental resource grouping, and retry guidance instead of a raw file list.

## Next Market-Facing Improvements

1. Add checked-in golden baselines for Paper Map, Paper Lens, Roadmap, and the start page, then run them in CI whenever frontend assets or report renderers change.
2. Promote release-history summaries into CI artifacts once the repository has checked-in visual baselines and browser interaction probes for the main report surfaces.
3. Deepen the `evidence_coverage.md` matrix by linking each mastery-readiness action to the exact missing paragraph, local note, downloaded-resource chunk, or task artifact.
4. Keep strengthening the guided mastery worksheet by adding richer per-slot source anchors, readiness status sync back into `roadmap.html`, and clearer "ready to present" checkpoints.
