---
name: ai-cs-learning-path
description: Generate AI/CS learning roadmaps from a learner profile, language preference, and multi-source resources. Use when the user wants to learn an AI/CS topic, build a study plan, choose Chinese or English resources, discover GitHub/video/course/paper materials, or create a roadmap from current knowledge to a target outcome.
---

# AI/CS Learning Path

Use this skill to build a personalized AI/CS learning roadmap.

## Workflow

1. Interview the learner:
   - Goal type: paper deep reading, skill mastery, project reproduction, exam/interview prep.
   - Current level by area: math, programming, ML/DL, systems, paper reading.
   - Known topics and blockers.
   - Weekly time budget and target date.
   - Output language: `zh-CN`, `en`, or `bilingual`.
   - Resource language: `zh-first`, `en-first`, `balanced`, `zh-only`, or `en-only`.
2. Call MCP tools or CLI:
   - `assessKnowledge`
   - `discoverSources`
   - `searchResources`
   - `rankResources`
   - `buildRoadmap`
   - `validateSources`
3. Prefer high-trust sources:
   - Primary papers, official docs, university courses, maintained GitHub repos, structured notebooks.
   - Use videos and community posts for intuition, not as sole authority.
4. Apply safety rules:
   - Do not use pirate libraries or Z-Lib mirrors.
   - Do not bypass login or scrape restricted pages.
   - Do not download videos.
   - Summarize and link copyrighted content instead of copying long excerpts.
5. Output:
   - `learner_profile.json`
   - `resource_index.json`
   - `source_registry_snapshot.json`
   - `roadmap.md`
   - `roadmap.json`

## CLI Examples

```bash
git4study roadmap --goal "从 Python 到掌握 Transformer" --output-language zh-CN --resource-language en-first --offline
git4study discover-sources --goal "理解 diffusion models" --language balanced
git4study ingest-url https://github.com/karpathy/nanoGPT
```
