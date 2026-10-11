# Research workbench examples

These are three **source-bounded demonstrations**, not human evaluation results or full-paper reproductions. [Source records](source_records.json) pin original links/versions, supplied coverage, missing materials, and content rights. Only original short paraphrases and metadata are bundled; no third-party paper text, code, figures, datasets, or benchmark logs are redistributed. All original generator/notes/toy materials use the [MIT license](LICENSE); that license does not cover linked papers.

| Scenario | Supplied | Intentionally absent |
| --- | --- | --- |
| planning-paper | Authored short abstract-level note of RAP, version 2305.14992v1; present goal. | Full paper, implementation, configuration, raw results. |
| transformer-paper-project | Authored short abstract-level note, version 1706.03762v7, plus original scalar-attention code/configuration/expected JSON/CSV trace; extend goal. | Full Transformer, author code, training, datasets, checkpoints, measured translation results. **Own toy demonstration, NOT actual paper reproduction.** |
| diffusion-missing-materials | Authored short abstract-level note, version 2006.11239v2; extend goal. | Full method/equations, code, schedule/configuration, datasets, raw results. Do not fill these gaps with synthetic experiments. |

## Generate locally

From the repository root, after the research-context/learning-path/explanation/export modules are integrated:

```bash
python -m pip install -e .
python examples/research-workbench/generate.py --output-dir ./examples/research-workbench/generated
python -m pytest -q examples/research-workbench/test_generate.py
```

The default writes `roadmap.json`, source/license records, and copied `study-assets` for each scenario, plus `example_manifest.json`. It does **not** generate HTML, take screenshots, or invent scores. It uses the shared application pipeline with `offline=True` and local explanations even when external-model environment variables are configured. No remote API, external LLM, embedding download, or project-code execution is used. Material hashes record the supplied bytes; missing modules produce a brief blocking message rather than a fake completed report.

Main's HTML export step uses the same exporter as the product:

```bash
python examples/research-workbench/generate.py --output-dir ./examples/research-workbench/generated --export-html
```

This produces `index.html`, `paper_map.html`, `paper_lens.html`, and `roadmap.html` in each scenario directory. Open each scenario's `index.html` directly. The B workbench has steps on the left, map/paragraph text in the center, and explanations/source anchors on the right. Paraphrase source locations refer to the **authored local note**, not an invented page in the paper. Original paper links are secondary provenance and are never fetched by the generator.

`exported_unverified` means only that HTML was written. If frontend assets are still being built, main must regenerate after the build. Inspect actual sections/segments and relationships, local links, source fingerprints, gap states, and desktop/mobile layouts before treating the reports as delivery evidence. No screenshot is checked in by this generator. Main owns real screenshot capture and visual/interaction verification; human study outcomes remain pending.

For each scenario, main can capture real screenshots and probe exported HTML after regeneration:

```bash
fields-study-flow audit-report --report-dir ./examples/research-workbench/generated/planning-paper --capture-screenshots --probe-interactions
```

Repeat for transformer-paper-project and diffusion-missing-materials. Optional browser dependencies are described in the root README. Preserve actual capture status/errors and do not substitute placeholder images. An audit score or passing screenshot is not a participant learning score.

## Inspect and hand off

Check a planning claim against the local note and then the versioned original source. In the Transformer case locate `scalar_attention`, `config.json`, and the expected trace; keep every automatic paper/code link unreviewed until checked, and keep the demonstration-versus-paper distinction visible. In the diffusion case, implementation/results steps must show missing materials and a next acquisition/check, never a fabricated method or score. Generated scaffolds are future tasks, not supplied evidence.

Move each **entire scenario folder**, including `study-assets`, `source_record.json`, and `LICENSE`. Export personal answers/notes separately as `study_state.json`; do not include them in a public example by default. On source changes, recheck affected locators and answers. Rerunning the generator does not manufacture a completed reproduction or independent mastery record.

See the [8-12-person protocol](../../docs/evaluation/research-understanding-protocol.md) for a strong same-model/tool-budget comparison, counterbalanced different materials, independent scoring, and retained failures. Recruitment, all human results, measured time savings, and comparative benefit are pending.

Contributions: improve a parser with a narrow fixture; correct an explanation with a versioned source; add an original/licensed case with an explicit gap boundary; or submit a reproducible UI issue with sanitized actual captures. Do not add a claimed benchmark outcome without its authorized raw evidence.
