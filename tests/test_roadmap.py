import json

from fields_study_flow.language import ResourceLanguagePreference
from fields_study_flow.models import LearnerProfile, Resource
from fields_study_flow.offline_catalog import offline_resources_for_goal
from fields_study_flow.ranking import rank_resources
from fields_study_flow.roadmap import build_roadmap, render_html, render_markdown, render_svg, sanitize_roadmap_for_export, write_outputs


def test_build_roadmap_contains_required_files_and_resource_fields():
    profile = LearnerProfile(
        goal="从线代概率到理解 diffusion models",
        output_language="zh-CN",
        resource_language_preference=ResourceLanguagePreference.BALANCED,
        weekly_hours=8,
        levels={"math": "beginner", "ml_dl": "familiar"},
    )
    resources = [
        Resource(
            title="Diffusion Models Course",
            url="https://example.com/diffusion",
            source="youtube",
            type="video",
            language="en",
            difficulty="intermediate",
            concepts=["diffusion models", "score matching"],
            estimated_time="3h",
            trust_score=0.9,
            why_recommended="Strong visual intuition.",
            license_or_access_note="Public video page.",
            translation_note="Use Chinese notes in the roadmap.",
        )
    ]

    roadmap = build_roadmap(profile, resources)

    assert roadmap["profile"]["goal"] == profile.goal
    assert roadmap["outputs"][:8] == [
        "learner_profile.json",
        "resource_index.json",
        "local_resource_analysis.json",
        "source_registry_snapshot.json",
        "roadmap.md",
        "roadmap.json",
        "roadmap.svg",
        "roadmap.html",
    ]
    assert "artifact_template/README.md" in roadmap["outputs"]
    assert roadmap["path_strategy"]["mode"] == "balanced"
    assert roadmap["path_strategy"]["mastery_standard"] == "explain_derive_reproduce_critique"
    assert "mastery_graph" in roadmap
    resource = roadmap["phases"][0]["resources"][0]
    for field in (
        "title",
        "url",
        "source",
        "type",
        "language",
        "difficulty",
        "prerequisites",
        "concepts",
        "estimated_time",
        "estimated_minutes",
        "learning_key_points",
        "focus_areas",
        "critical_path_role",
        "trust_score",
        "why_recommended",
        "license_or_access_note",
        "translation_note",
    ):
        assert field in resource


def test_write_outputs_writes_paper_lens_for_target_paper(tmp_path):
    profile = LearnerProfile(goal="master Teaching LLMs to Plan", output_language="zh-CN", target_kind="paper")
    target = Resource(
        title="Teaching LLMs to Plan",
        url="local://paper-teaching-llms-to-plan",
        source="local-library",
        type="paper",
        concepts=["symbolic planning", "logical chain-of-thought"],
        estimated_minutes=180,
        critical_path_role="core-paper",
        metadata={
            "target_paper": True,
            "paper_metadata": {
                "title": "Teaching LLMs to Plan: Logical Chain-of-Thought Instruction Tuning for Symbolic Planning",
                "abstract_snippet": "The paper teaches LLMs to produce planning traces.",
                "authors": ["Example Author"],
                "concepts": ["symbolic planning", "PDDL"],
                "sections": ["Introduction", "Method", "Experiments", "Limitations"],
                "method_hints": ["The method creates logical chain-of-thought traces."],
                "experiment_hints": ["Experiments evaluate planning validity."],
                "limitations_hints": ["Coverage of planning domains remains limited."],
                "metadata_status": "ok",
                "local_path": None,
            },
        },
    )
    support = Resource(
        title="PDDL Notes",
        url="https://planning.wiki/ref/pddl",
        source="documentation",
        type="documentation",
        concepts=["PDDL", "planning"],
        learning_key_points=["PDDL action preconditions determine applicability."],
        estimated_minutes=45,
    )

    roadmap = build_roadmap(profile, [target, support])
    write_outputs(tmp_path, profile, [target, support], roadmap, {})

    exported = json.loads((tmp_path / "roadmap.json").read_text(encoding="utf-8"))
    assert "paper_lens" in exported
    assert "paper_lens.html" in exported["outputs"]
    assert (tmp_path / "paper_lens.html").exists()
    assert "目标论文增强阅读器" in (tmp_path / "paper_lens.html").read_text(encoding="utf-8")
    assert "paper_lens.html" in (tmp_path / "roadmap.html").read_text(encoding="utf-8")


def test_sanitize_roadmap_keeps_public_https_urls_while_redacting_private_paths():
    public = sanitize_roadmap_for_export(
        {
            "title": "Learning Roadmap: https://arxiv.org/abs/1706.03762",
            "phases": [
                {
                    "resources": [
                        {
                            "title": "Attention Is All You Need",
                            "url": "https://arxiv.org/abs/1706.03762",
                            "why_recommended": "Private note at C:/Users/example/private/paper.pdf",
                            "local_path": "C:/Users/example/private/paper.pdf",
                        }
                    ]
                }
            ],
        }
    )
    dumped = str(public)

    assert "https://arxiv.org/abs/1706.03762" in dumped
    assert "C:/Users/example/private" not in dumped
    assert public["phases"][0]["resources"][0]["local_path"] is None


def test_bilingual_roadmap_keeps_both_language_labels():
    profile = LearnerProfile(
        goal="Understand and reproduce PPO/TRPO",
        output_language="bilingual",
        resource_language_preference=ResourceLanguagePreference.EN_FIRST,
    )

    roadmap = build_roadmap(profile, [])

    assert "Learning Roadmap" in roadmap["title"]
    assert "学习路线" in roadmap["title"]


def test_report_labels_follow_output_language_selection():
    resource = Resource(
        title="Transformer Notes",
        url="https://example.com/transformer",
        source="course",
        type="article",
        language="en",
        concepts=["transformer"],
        estimated_minutes=60,
        trust_score=0.8,
        critical_path_role="focused-support",
    )

    zh = build_roadmap(LearnerProfile(goal="掌握 Transformer", output_language="zh-CN"), [resource])
    en = build_roadmap(LearnerProfile(goal="master Transformer", output_language="en"), [resource])
    bilingual = build_roadmap(LearnerProfile(goal="掌握 Transformer", output_language="bilingual"), [resource])

    zh_md = render_markdown(zh)
    zh_html = render_html(zh)
    zh_svg = render_svg(zh)
    en_md = render_markdown(en)
    bilingual_md = render_markdown(bilingual)
    bilingual_html = render_html(bilingual)

    assert "## 掌握路径策略" in zh_md
    assert "<b>目标</b>" in zh_html
    assert "掌握图谱" in zh_html
    assert "模式" in zh_svg
    assert "## Mastery Path Strategy" in en_md
    assert "## Mastery Path Strategy / 掌握路径策略" in bilingual_md
    assert "Goal / 目标" in bilingual_html


def test_build_roadmap_keeps_shortest_mastery_path_not_every_candidate():
    profile = LearnerProfile(goal="fully master Transformer paper", output_language="en", weekly_hours=4)
    target = Resource(
        title="Attention Is All You Need",
        url="https://arxiv.org/abs/1706.03762",
        source="arxiv",
        type="paper",
        language="en",
        concepts=["transformer", "attention"],
        estimated_time="6h",
        estimated_minutes=360,
        trust_score=0.97,
        metadata={"target_paper": True},
        critical_path_role="core-paper",
    )
    shortcut = Resource(
        title="Local Transformer derivation notes",
        url="file:///notes/transformer.md",
        source="local-library",
        type="notes",
        language="en",
        concepts=["transformer", "attention"],
        estimated_time="30min",
        estimated_minutes=30,
        trust_score=0.75,
        metadata={"local_availability": True, "candidate_decision": "critical-path-candidate"},
        critical_path_role="focused-support",
    )
    long_detour = Resource(
        title="Large generic ML course",
        url="https://example.com/ml",
        source="course",
        type="course",
        language="en",
        concepts=["machine learning"],
        estimated_time="40h",
        estimated_minutes=2400,
        trust_score=0.8,
    )

    roadmap = build_roadmap(profile, [target, shortcut, long_detour])
    selected_titles = [resource["title"] for phase in roadmap["phases"] for resource in phase["resources"]]

    assert "Attention Is All You Need" in selected_titles
    assert "Local Transformer derivation notes" in selected_titles
    assert "Large generic ML course" not in selected_titles
    library_titles = [resource["title"] for resource in roadmap["resource_library"]]
    omitted = next(resource for resource in roadmap["resource_library"] if resource["title"] == "Large generic ML course")
    assert library_titles == ["Attention Is All You Need", "Local Transformer derivation notes", "Large generic ML course", "fields-study-flow-template"]
    assert omitted["route_status"] == "omitted"
    assert omitted["route_reason"] in {"broad-detour", "lower-marginal-value", "off-target"}
    assert roadmap["path_strategy"]["selected_resources"] < roadmap["path_strategy"]["candidate_resources"]


def test_build_roadmap_excludes_local_resource_that_adds_no_coverage():
    profile = LearnerProfile(goal="fully master Transformer paper", output_language="en")
    target = Resource(
        title="Attention Is All You Need",
        url="https://arxiv.org/abs/1706.03762",
        source="arxiv",
        type="paper",
        language="en",
        concepts=["transformer", "attention"],
        estimated_minutes=360,
        trust_score=0.97,
        metadata={"target_paper": True},
        critical_path_role="core-paper",
    )
    unrelated_local = Resource(
        title="Grocery List",
        url="local://local-grocery",
        source="local-library",
        type="notes",
        language="en",
        concepts=["grocery"],
        estimated_minutes=20,
        local_path="/private/user/grocery-list.md",
        metadata={"local_availability": True, "candidate_decision": "supplement-only", "local_resource_id": "local-grocery"},
        critical_path_role="focused-support",
    )

    roadmap = build_roadmap(profile, [target, unrelated_local])
    selected = [resource for phase in roadmap["phases"] for resource in phase["resources"]]

    assert [resource["title"] for resource in selected] == ["Attention Is All You Need", "fields-study-flow-template"]
    assert selected[0]["local_path"] is None
    assert all(resource["title"] != "Grocery List" for resource in selected)


def test_build_roadmap_redacts_private_local_paths_in_shareable_outputs():
    profile = LearnerProfile(goal="master local Transformer notes", output_language="en")
    local = Resource(
        title="Transformer Notes",
        url="local://local-notes",
        source="local-library",
        type="notes",
        language="en",
        concepts=["transformer"],
        estimated_minutes=30,
        local_path="/Users/example/private/transformer-notes.md",
        metadata={"local_availability": True, "candidate_decision": "critical-path-candidate", "local_resource_id": "local-notes"},
        critical_path_role="focused-support",
    )

    roadmap = build_roadmap(profile, [local])
    resource = roadmap["phases"][0]["resources"][0]

    assert resource["url"] == "local://local-notes"
    assert resource["local_path"] is None


def test_route_depth_changes_resource_count_for_same_candidates():
    resources = [
        Resource(
            title="Attention Is All You Need",
            url="https://arxiv.org/abs/1706.03762",
            source="arxiv",
            type="paper",
            language="en",
            concepts=["transformer", "attention"],
            estimated_minutes=360,
            trust_score=0.97,
            metadata={"target_paper": True},
            critical_path_role="core-paper",
        ),
        Resource(
            title="Transformer intuition",
            url="https://example.com/intuition",
            source="course",
            type="article",
            language="en",
            concepts=["transformer", "attention"],
            estimated_minutes=90,
            trust_score=0.85,
            critical_path_role="focused-support",
        ),
        Resource(
            title="Transformer reproduction repo",
            url="https://github.com/example/transformer-repro",
            source="github",
            type="repository",
            language="en",
            concepts=["transformer", "python"],
            estimated_minutes=480,
            trust_score=0.9,
            critical_path_role="practice-validation",
            metadata={"has_curriculum": True},
        ),
        Resource(
            title="Transformer limitations survey",
            url="https://example.com/limits",
            source="openalex",
            type="paper",
            language="en",
            concepts=["transformer", "limitations"],
            estimated_minutes=180,
            trust_score=0.82,
            critical_path_role="focused-support",
        ),
    ]

    fastest = build_roadmap(LearnerProfile(goal="master Transformer paper", output_language="en", route_depth="fastest"), resources)
    balanced = build_roadmap(LearnerProfile(goal="master Transformer paper", output_language="en", route_depth="balanced"), resources)
    complete = build_roadmap(LearnerProfile(goal="master Transformer paper", output_language="en", route_depth="complete"), resources)

    assert fastest["path_strategy"]["selected_resources"] <= balanced["path_strategy"]["selected_resources"]
    assert balanced["path_strategy"]["selected_resources"] <= complete["path_strategy"]["selected_resources"]
    assert complete["path_strategy"]["route_depth"] == "complete"


def test_paper_roadmap_contains_mastery_tasks_for_explanation_derivation_reproduction_and_critique():
    profile = LearnerProfile(goal="fully master Transformer paper", output_language="en", target_kind="paper")
    target = Resource(
        title="Attention Is All You Need",
        url="https://arxiv.org/abs/1706.03762",
        source="arxiv",
        type="paper",
        language="en",
        concepts=["transformer", "attention"],
        estimated_minutes=360,
        trust_score=0.97,
        metadata={"target_paper": True},
        critical_path_role="core-paper",
    )

    roadmap = build_roadmap(profile, [target])
    task_labels = [node["label"] for node in roadmap["mastery_graph"]["nodes"] if node["kind"] == "task"]

    assert any("Explain" in label for label in task_labels)
    assert any("Derive" in label for label in task_labels)
    assert any("Reproduce" in label for label in task_labels)
    assert any("Critique" in label for label in task_labels)


def test_build_roadmap_includes_lightweight_knowledge_graph_without_rag():
    roadmap = build_roadmap(
        LearnerProfile(goal="master PDDL planning", output_language="en", target_kind="field"),
        [
            Resource(
                title="PDDL Notes",
                url="https://example.com/pddl",
                source="documentation",
                type="article",
                language="en",
                concepts=["PDDL", "symbolic planning"],
                learning_key_points=["action preconditions"],
                focus_areas=["VAL plan validation"],
                critical_path_role="focused-support",
                estimated_minutes=90,
            )
        ],
    )

    graph = roadmap["knowledge_graph"]
    assert graph["summary"]["concepts"] >= 1
    assert graph["summary"]["resources"] >= 1
    assert graph["summary"]["tasks"] >= 1
    assert graph["summary"]["assessments"] == 1
    assert any(edge["label"] == "covered_by" for edge in graph["edges"])
    assert any(edge["label"] == "required_for" for edge in graph["edges"])


def test_field_roadmap_infers_project_or_survey_artifact_from_goal():
    engineering = build_roadmap(
        LearnerProfile(goal="build a diffusion model project", output_language="en", target_kind="field"),
        [
            Resource(
                title="Diffusion implementation guide",
                url="https://example.com/diffusion-code",
                source="github",
                type="repository",
                language="en",
                concepts=["diffusion models", "python"],
                estimated_minutes=300,
                trust_score=0.8,
            )
        ],
    )
    research = build_roadmap(
        LearnerProfile(goal="write a survey of diffusion model papers", output_language="en", target_kind="field"),
        [
            Resource(
                title="Diffusion Models Beat GANs",
                url="https://arxiv.org/abs/2105.05233",
                source="arxiv",
                type="paper",
                language="en",
                concepts=["diffusion models"],
                estimated_minutes=300,
                trust_score=0.9,
            )
        ],
    )

    assert engineering["final_artifact"]["type"] == "project"
    assert research["final_artifact"]["type"] == "survey"


def test_project_roadmap_injects_generated_template_when_no_runnable_resource():
    roadmap = build_roadmap(
        LearnerProfile(goal="build a diffusion model project", output_language="en", target_kind="field"),
        [
            Resource(
                title="Diffusion Models Beat GANs",
                url="https://arxiv.org/abs/2105.05233",
                source="arxiv",
                type="paper",
                language="en",
                concepts=["diffusion models"],
                estimated_minutes=300,
                trust_score=0.9,
                critical_path_role="core-paper",
            )
        ],
    )

    phase_resources = [resource for phase in roadmap["phases"] for resource in phase["resources"]]
    generated = [resource for resource in phase_resources if resource["metadata"].get("generated_template")]

    assert roadmap["artifact_requirements"]["requires_runnable"] is True
    assert roadmap["artifact_requirements"]["policy"] == "auto-generated-template"
    assert roadmap["artifact_gaps"]
    assert roadmap["artifact_gaps"][0]["status"] == "template-required"
    assert generated
    assert generated[0]["critical_path_role"] == "practice-validation"
    assert "artifact_template/README.md" in roadmap["generated_artifacts"]


def test_chinese_project_goal_requires_verifiable_artifact_template():
    roadmap = build_roadmap(
        LearnerProfile(goal="复现 diffusion model 并完成一个小项目", output_language="zh-CN", target_kind="field"),
        [
            Resource(
                title="Diffusion Models Beat GANs",
                url="https://arxiv.org/abs/2105.05233",
                source="arxiv",
                type="paper",
                language="en",
                concepts=["diffusion models"],
                estimated_minutes=300,
                trust_score=0.9,
                critical_path_role="core-paper",
            )
        ],
    )

    assert roadmap["artifact_requirements"]["requires_runnable"] is True
    assert roadmap["artifact_requirements"]["policy"] == "auto-generated-template"
    assert roadmap["artifact_gaps"][0]["status"] == "template-required"


def test_project_roadmap_does_not_generate_template_when_runnable_resource_exists():
    roadmap = build_roadmap(
        LearnerProfile(goal="build a diffusion model project", output_language="en", target_kind="field"),
        [
            Resource(
                title="Diffusion implementation",
                url="https://github.com/example/diffusion",
                source="github",
                type="repository",
                language="en",
                concepts=["diffusion models", "python"],
                estimated_minutes=300,
                trust_score=0.8,
                critical_path_role="practice-validation",
            )
        ],
    )

    phase_resources = [resource for phase in roadmap["phases"] for resource in phase["resources"]]

    assert roadmap["artifact_requirements"]["requires_runnable"] is True
    assert roadmap["artifact_requirements"]["policy"] == "existing-runnable-resource"
    assert roadmap["generated_artifacts"] == []
    assert not any(resource["metadata"].get("generated_template") for resource in phase_resources)


def test_artifact_enforcement_uses_template_instead_of_unrelated_runnable_candidate():
    roadmap = build_roadmap(
        LearnerProfile(goal="fully understand, derive, and reproduce arxiv 9999.00000", output_language="en", target_kind="paper"),
        [
            Resource(
                title="Unknown target paper",
                url="https://arxiv.org/abs/9999.00000",
                source="arxiv",
                type="paper",
                language="en",
                concepts=["paper reading"],
                estimated_minutes=300,
                trust_score=0.9,
                metadata={"target_paper": True},
                critical_path_role="core-paper",
            ),
            Resource(
                title="Generic machine learning derivation repository",
                url="https://github.com/example/generic-ml",
                source="github",
                type="repository",
                language="en",
                concepts=["machine learning", "derivation"],
                estimated_minutes=600,
                trust_score=0.7,
                critical_path_role="practice-validation",
            ),
        ],
    )

    selected_titles = [resource["title"] for phase in roadmap["phases"] for resource in phase["resources"]]

    assert "fields-study-flow-template" in selected_titles
    assert "Generic machine learning derivation repository" not in selected_titles
    assert roadmap["artifact_requirements"]["policy"] == "auto-generated-template"


def test_fastest_route_replaces_broad_prerequisite_with_focused_sprint():
    roadmap = build_roadmap(
        LearnerProfile(goal="fully master Transformer paper", output_language="en", target_kind="paper", route_depth="fastest"),
        [
            Resource(
                title="Attention Is All You Need",
                url="https://arxiv.org/abs/1706.03762",
                source="arxiv",
                type="paper",
                language="en",
                concepts=["transformer", "attention"],
                estimated_minutes=360,
                trust_score=0.97,
                metadata={"target_paper": True},
                critical_path_role="core-paper",
            ),
            Resource(
                title="Mathematics for Machine Learning",
                url="https://mml-book.github.io/",
                source="course",
                type="book",
                language="en",
                difficulty="beginner",
                concepts=["linear algebra", "probability", "optimization"],
                estimated_minutes=720,
                trust_score=0.92,
                critical_path_role="prerequisite",
            ),
        ],
    )

    selected = [resource for phase in roadmap["phases"] for resource in phase["resources"]]
    selected_titles = [resource["title"] for resource in selected]

    assert "Focused prerequisite sprint" in selected_titles
    assert "Mathematics for Machine Learning" not in selected_titles
    assert next(resource for resource in selected if resource["title"] == "Focused prerequisite sprint")["estimated_minutes"] <= 120


def test_fastest_paper_route_keeps_cap_after_generated_template_injection():
    roadmap = build_roadmap(
        LearnerProfile(
            goal="fully master a private paper with attention sampling optimization evaluation calibration",
            output_language="en",
            target_kind="paper",
            route_depth="fastest",
        ),
        [
            Resource(
                title="Private target paper",
                url="local://paper-private",
                source="local-library",
                type="paper",
                language="en",
                concepts=["private method", "attention"],
                estimated_minutes=360,
                trust_score=0.8,
                metadata={"target_paper": True},
                critical_path_role="core-paper",
            ),
            Resource(
                title="Attention intuition",
                url="https://example.com/attention",
                source="course",
                type="article",
                language="en",
                concepts=["attention"],
                estimated_minutes=90,
                trust_score=0.82,
                critical_path_role="focused-support",
            ),
            Resource(
                title="Sampling optimization background",
                url="https://example.com/background",
                source="course",
                type="article",
                language="en",
                concepts=["sampling", "optimization"],
                estimated_minutes=90,
                trust_score=0.8,
                critical_path_role="focused-support",
            ),
            Resource(
                title="Evaluation calibration guide",
                url="https://example.com/evaluation",
                source="course",
                type="article",
                language="en",
                concepts=["evaluation", "calibration"],
                estimated_minutes=90,
                trust_score=0.79,
                critical_path_role="focused-support",
            ),
        ],
    )

    selected_titles = [resource["title"] for phase in roadmap["phases"] for resource in phase["resources"]]

    assert "fields-study-flow-template" in selected_titles
    assert roadmap["path_strategy"]["selected_resources"] <= 3
    assert len(selected_titles) <= 3


def test_balanced_practical_project_uses_focused_prerequisite_sprint():
    roadmap = build_roadmap(
        LearnerProfile(goal="build a diffusion model project", output_language="en", target_kind="field", route_depth="balanced", learning_style="practical"),
        [
            Resource(
                title="Mathematics for Machine Learning",
                url="https://mml-book.github.io/",
                source="course",
                type="book",
                language="en",
                difficulty="beginner",
                concepts=["linear algebra", "probability", "optimization"],
                estimated_minutes=720,
                trust_score=0.92,
                critical_path_role="prerequisite",
            ),
            Resource(
                title="Diffusion guide",
                url="https://example.com/diffusion",
                source="course",
                type="article",
                language="en",
                concepts=["diffusion models", "score matching"],
                estimated_minutes=180,
                trust_score=0.8,
                critical_path_role="focused-support",
            ),
        ],
    )

    selected_titles = [resource["title"] for phase in roadmap["phases"] for resource in phase["resources"]]

    assert "Focused prerequisite sprint" in selected_titles
    assert "Mathematics for Machine Learning" not in selected_titles
    assert roadmap["path_strategy"]["estimated_total_minutes"] < 720


def test_mastery_graph_binds_generated_template_to_reproduction_task():
    roadmap = build_roadmap(
        LearnerProfile(goal="fully understand and reproduce a diffusion paper", output_language="en", target_kind="paper"),
        [
            Resource(
                title="Diffusion paper",
                url="https://arxiv.org/abs/2105.05233",
                source="arxiv",
                type="paper",
                language="en",
                concepts=["diffusion models"],
                estimated_minutes=300,
                trust_score=0.9,
                metadata={
                    "target_paper": True,
                    "paper_metadata": {
                        "title": "Diffusion paper",
                        "abstract_snippet": "A paper about diffusion model sampling.",
                        "authors": ["Ada Example"],
                        "sections": ["Method", "Experiments"],
                        "concepts": ["diffusion models"],
                    },
                },
                critical_path_role="core-paper",
            )
        ],
    )
    nodes = {node["label"]: node["id"] for node in roadmap["mastery_graph"]["nodes"]}
    edges = roadmap["mastery_graph"]["edges"]

    assert any(
        edge["from"] == nodes["fields-study-flow-template"]
        and edge["to"] == nodes["Reproduce the minimal method or experiment"]
        and edge["label"] == "supports_reproduce"
        for edge in edges
    )
    assert any(edge["label"] == "required_for" for edge in edges)


def test_reports_show_paper_metadata_and_artifact_requirements_without_private_paths():
    roadmap = build_roadmap(
        LearnerProfile(goal="fully understand and reproduce a diffusion paper", output_language="en", target_kind="paper"),
        [
            Resource(
                title="Diffusion paper",
                url="local://paper-diffusion",
                source="local-library",
                type="paper",
                language="en",
                concepts=["diffusion models"],
                estimated_minutes=300,
                trust_score=0.9,
                local_path="C:/Users/example/private/diffusion.pdf",
                metadata={
                    "target_paper": True,
                    "paper_metadata": {
                        "title": "Diffusion paper",
                        "abstract_snippet": "A paper about diffusion model sampling.",
                        "authors": ["Ada Example"],
                        "sections": ["Method", "Experiments"],
                        "concepts": ["diffusion models"],
                        "keywords": ["diffusion models", "sampling"],
                        "formula_candidates": ["L_simple = E[||epsilon - epsilon_theta(x_t,t)||^2]"],
                        "code_links": ["https://github.com/example/diffusion-sampler"],
                        "local_path": None,
                    },
                },
                critical_path_role="core-paper",
            )
        ],
    )

    markdown = render_markdown(roadmap)
    html = render_html(roadmap)
    svg = render_svg(roadmap)

    assert "## Paper Metadata" in markdown
    assert "Formula candidates" in markdown
    assert "epsilon_theta" in markdown
    assert "https://github.com/example/diffusion-sampler" in markdown
    assert "## Artifact Requirements" in markdown
    assert "## Artifact Gaps" in markdown
    assert "template-required" in markdown
    assert "artifact_template/README.md" in markdown
    assert "Paper Metadata" in svg
    assert "Artifact Requirements" in svg
    assert "Artifact Gaps" in svg
    assert "template-required" in svg
    assert "artifact_template/README.md" in svg
    assert "paper-metadata-panel" in html
    assert "epsilon_theta" in html
    assert "github.com/example/diffusion-sampler" in html
    assert "artifact-panel" in html
    assert "artifact-gaps-panel" in html
    assert "template-required" in html
    assert "overflow-wrap:anywhere" in html
    assert "@media (max-width:520px)" in html
    assert ".summary-grid, .info-grid, .mini-grid { grid-template-columns:1fr; }" in html
    assert "C:/Users/example/private/diffusion.pdf" not in markdown
    assert "C:/Users/example/private/diffusion.pdf" not in html
    assert "C:/Users/example/private/diffusion.pdf" not in svg


def test_render_html_escapes_private_paths_and_wraps_long_text():
    roadmap = build_roadmap(
        LearnerProfile(goal="master local Transformer notes", output_language="en"),
        [
            Resource(
                title="Very Long Transformer Resource Title That Should Wrap Without Escaping Its Card Boundary",
                url="local://local-notes",
                source="local-library",
                type="notes",
                language="en",
                concepts=["transformer"],
                estimated_minutes=30,
                local_path="C:/Users/example/private/transformer-notes.md",
                metadata={"local_availability": True, "candidate_decision": "critical-path-candidate", "local_resource_id": "local-notes"},
                critical_path_role="focused-support",
            )
        ],
    )

    html = render_html(roadmap)

    assert "roadmap-grid" in html
    assert "overflow-wrap:anywhere" in html
    assert "h1, h2, h3, p, li, span, a { overflow-wrap:anywhere; word-break:break-word; }" in html
    assert ".summary-card span { display:block;" in html
    assert "C:/Users/example/private/transformer-notes.md" not in html
    assert "local://local-notes" in html


def test_roadmap_explains_shortest_route_and_exposes_quality_gates():
    roadmap = build_roadmap(
        LearnerProfile(goal="fully master Transformer paper", output_language="en", target_kind="paper", route_depth="fastest"),
        [
            Resource(
                title="Attention Is All You Need",
                url="https://arxiv.org/abs/1706.03762",
                source="arxiv",
                type="paper",
                language="en",
                concepts=["transformer", "attention"],
                estimated_minutes=360,
                trust_score=0.97,
                metadata={"target_paper": True},
                critical_path_role="core-paper",
            ),
            Resource(
                title="Transformer reproduction notebook",
                url="https://github.com/example/transformer-notebook",
                source="github",
                type="notebook",
                language="en",
                concepts=["transformer", "python"],
                estimated_minutes=180,
                trust_score=0.86,
                critical_path_role="practice-validation",
            ),
            Resource(
                title="Large generic ML course",
                url="https://example.com/ml",
                source="course",
                type="course",
                language="en",
                concepts=["machine learning"],
                estimated_minutes=2400,
                trust_score=0.8,
                critical_path_role="prerequisite",
            ),
        ],
    )

    assert roadmap["route_audit"]["omitted_resources"]
    assert roadmap["route_audit"]["omitted_resources"][0]["reason"] in {"broad-detour", "lower-marginal-value"}
    assert roadmap["route_audit"]["coverage_ratio"] >= 0.66
    assert len(roadmap["study_tasks"]) == 4
    assert {task["type"] for task in roadmap["study_tasks"]} == {"explain", "derive", "reproduce", "critique"}
    assert all(task["evidence"] for task in roadmap["study_tasks"])
    assert roadmap["next_actions"][0]["task_id"] == roadmap["study_tasks"][0]["id"]
    assert set(roadmap["quality_report"]["dimensions"]) == {"usefulness", "usability", "convenience", "novelty", "completeness"}
    assert all(item["level"] == "high" for item in roadmap["quality_report"]["dimensions"].values())


def test_roadmap_builds_mastery_evidence_contract_for_verifiable_learning():
    roadmap = build_roadmap(
        LearnerProfile(goal="fully master Transformer paper", output_language="en", target_kind="paper", route_depth="fastest"),
        [
            Resource(
                title="Attention Is All You Need",
                url="https://arxiv.org/abs/1706.03762",
                source="arxiv",
                type="paper",
                language="en",
                concepts=["transformer", "attention"],
                estimated_minutes=360,
                trust_score=0.97,
                metadata={"target_paper": True},
                critical_path_role="core-paper",
            ),
            Resource(
                title="Transformer reproduction notebook",
                url="https://github.com/example/transformer-notebook",
                source="github",
                type="notebook",
                language="en",
                concepts=["transformer", "python"],
                estimated_minutes=180,
                trust_score=0.86,
                critical_path_role="practice-validation",
            ),
        ],
    )

    evidence = roadmap["mastery_evidence"]
    task_types = {item["task_type"] for item in evidence["required_evidence"]}
    markdown = render_markdown(roadmap)
    html = render_html(roadmap)

    assert evidence["status"] == "ready-for-evidence"
    assert evidence["claim"] == "Learning is not complete until every evidence item is filled and reviewable."
    assert {"explain", "derive", "reproduce", "critique"} <= task_types
    assert all(item["pass_criteria"] for item in evidence["required_evidence"])
    assert any("Transformer reproduction notebook" in item["resources"] for item in evidence["required_evidence"])
    assert "## Mastery Evidence" in markdown
    assert "mastery-evidence-panel" in html
    assert "Learning is not complete until every evidence item is filled" in html


def test_reports_show_quality_route_audit_and_next_actions():
    roadmap = build_roadmap(
        LearnerProfile(goal="build a diffusion model project", output_language="en", target_kind="field", route_depth="balanced"),
        [
            Resource(
                title="Diffusion guide",
                url="https://example.com/diffusion",
                source="course",
                type="article",
                language="en",
                concepts=["diffusion models", "score matching"],
                estimated_minutes=180,
                trust_score=0.8,
                critical_path_role="focused-support",
            )
        ],
    )

    markdown = render_markdown(roadmap)
    html = render_html(roadmap)
    svg = render_svg(roadmap)

    assert "## Plan Quality" in markdown
    assert "## Route Audit" in markdown
    assert "## Next Actions" in markdown
    assert "## Learning Resource Library" in markdown
    assert "quality-panel" in html
    assert "route-audit-panel" in html
    assert "next-actions-panel" in html
    assert "resource-library-panel" in html
    assert "library-grid" in html
    assert "Plan Quality" in svg


def test_reports_show_rag_evidence_panel_and_task_sources():
    roadmap = {
        "title": "Learning Roadmap: PDDL",
        "profile": {"goal": "master PDDL planning", "output_language": "en", "resource_language_preference": "balanced"},
        "path_strategy": {"mode": "fastest", "estimated_total_time": "1h", "selected_resources": 1, "candidate_resources": 1},
        "rag_evidence": {
            "mode": "light",
            "summary": {"chunks": 2, "resources": 1},
            "top_chunks": [
                {
                    "resource_title": "PDDL Notes",
                    "file_name": "01-pddl-notes.md",
                    "snippet": "Action preconditions decide whether a plan step can run.",
                    "score": 2.5,
                }
            ],
        },
        "mastery_evidence": {
            "status": "ready-for-evidence",
            "claim": "Evidence required.",
            "final_artifact": "paper-mastery",
            "required_evidence": [
                {
                    "task_type": "explain",
                    "evidence": "Explain it.",
                    "pass_criteria": "Grounded in evidence.",
                    "resources": ["PDDL Notes"],
                    "evidence_chunks": [
                        {
                            "resource_title": "PDDL Notes",
                            "file_name": "01-pddl-notes.md",
                            "snippet": "Action preconditions decide whether a plan step can run.",
                        }
                    ],
                    "review_status": "open",
                }
            ],
        },
        "knowledge_graph": {
            "summary": {"concepts": 1, "resources": 1, "tasks": 1, "assessments": 1, "edges": 3, "evidence_backed_edges": 1},
            "nodes": [
                {"id": "concept-1", "kind": "concept", "label": "Action preconditions"},
                {"id": "resource-1", "kind": "resource", "label": "PDDL Notes"},
                {"id": "task-1-explain", "kind": "task", "label": "Explain PDDL action preconditions"},
                {"id": "assessment-1", "kind": "assessment", "label": "paper-mastery"},
            ],
            "edges": [
                {"from": "concept-1", "to": "resource-1", "label": "covered_by"},
                {
                    "from": "resource-1",
                    "to": "task-1-explain",
                    "label": "supports",
                    "evidence_chunks": [
                        {
                            "resource_title": "PDDL Notes",
                            "file_name": "01-pddl-notes.md",
                            "snippet": "Action preconditions decide whether a plan step can run.",
                        }
                    ],
                },
                {"from": "task-1-explain", "to": "assessment-1", "label": "required_for"},
            ],
        },
        "phases": [],
        "checkpoints": [],
        "safety_policy": [],
    }

    markdown = render_markdown(roadmap)
    html = render_html(roadmap)

    assert "## Evidence" in markdown
    assert "Action preconditions decide" in markdown
    assert "rag-evidence-panel" in html
    assert "01-pddl-notes.md" in html
    assert "knowledge-graph-panel" in html
    assert "kg-flow" in html
    assert "kg-column" in html
    assert "kg-node" in html
    assert "kg-edge-chip" in html


def test_zh_report_localizes_generated_labels_fonts_and_interactions():
    roadmap = build_roadmap(
        LearnerProfile(goal="掌握 PDDL 规划论文", output_language="zh-CN", target_kind="paper"),
        [
            Resource(
                title="PDDL Planning Paper",
                url="https://arxiv.org/abs/2509.13351",
                source="arxiv",
                type="paper",
                language="en",
                concepts=["PDDL", "symbolic planning"],
                learning_key_points=["action preconditions"],
                focus_areas=["VAL plan validation"],
                critical_path_role="core-paper",
                metadata={"target_paper": True},
                estimated_minutes=180,
            )
        ],
    )
    html = render_html(roadmap)
    svg = render_svg(roadmap)

    assert 'class="interactive-roadmap"' in html
    assert "font-family:\"Microsoft YaHei UI\"" in html
    assert "font-family:'Microsoft YaHei UI'" in svg
    assert "解释问题、贡献和假设" in html
    assert "准备填写证据" in html
    assert "论文掌握" in html
    assert "Explain the problem" not in html
    assert "ready-for-evidence" not in html
    assert "paper-mastery" not in html
    assert "kg-node-button" in html
    assert "resource-library-filter" in html
    assert "evidence-toggle" in html
    assert "phase-collapse-button" in html
    assert "kg-edge-active" in html
    assert "addEventListener" in html
    assert roadmap["resource_library"][0]["localized"]["route_status"] in {"已选择", "已生成"}
    assert all("localized_label" in edge for edge in roadmap["knowledge_graph"]["edges"])


def test_zh_interactive_learning_console_network_filters_and_copy_are_localized():
    roadmap = build_roadmap(
        LearnerProfile(goal="掌握符号规划论文", output_language="zh-CN", target_kind="paper"),
        [
            Resource(
                title="PDDL Planning Paper",
                url="https://arxiv.org/abs/2509.13351",
                source="arxiv",
                type="paper",
                language="en",
                concepts=["PDDL", "symbolic planning"],
                learning_key_points=["action preconditions"],
                focus_areas=["VAL plan validation"],
                critical_path_role="core-paper",
                estimated_minutes=180,
            ),
            Resource(
                title="VAL Plan Validator",
                url="https://github.com/KCL-Planning/VAL",
                source="github",
                type="repository",
                language="en",
                concepts=["VAL", "plan validation"],
                learning_key_points=["validation workflow"],
                focus_areas=["runnable checks"],
                critical_path_role="practice-validation",
                estimated_minutes=120,
            ),
        ],
    )
    roadmap["rag_evidence"] = {
        "mode": "light",
        "summary": {"chunks": 4, "resources": 2},
        "top_chunks": [
            {
                "resource_title": "PDDL Planning Paper",
                "file_name": "paper.pdf",
                "snippet": "Action preconditions decide whether a plan step can run.",
                "score": 2.5,
            }
        ],
    }
    roadmap["study_bundle"] = {
        "bundle_scope": "all",
        "summary": {
            "total": 2,
            "downloaded": 1,
            "link-only": 1,
            "failed": 0,
            "retryable": 0,
            "downloaded_selected": 1,
            "downloaded_omitted": 0,
        },
        "resources": [
            {
                "index": 1,
                "title": "PDDL Planning Paper",
                "source": "arxiv",
                "type": "paper",
                "status": "downloaded",
                "route_status": "selected",
                "selected": True,
                "file": "01-pddl-planning-paper.pdf",
                "download_url": "https://arxiv.org/pdf/2509.13351",
                "retryable": False,
                "attempts": 1,
            },
            {
                "index": 2,
                "title": "VAL Plan Validator",
                "source": "github",
                "type": "repository",
                "status": "link-only",
                "route_status": "omitted",
                "selected": False,
                "file": "",
                "download_url": "https://github.com/KCL-Planning/VAL",
                "retryable": False,
                "attempts": 0,
                "reason": "manual link only",
            },
        ],
    }
    roadmap["mastery_evidence"]["status"] = "ready-for-evidence"
    roadmap["mastery_evidence"]["final_artifact"] = "paper-mastery"
    roadmap["final_artifact"]["type"] = "paper-mastery"
    if roadmap["mastery_evidence"].get("required_evidence"):
        roadmap["mastery_evidence"]["required_evidence"][0]["task_type"] = "explain"
        roadmap["mastery_evidence"]["required_evidence"][0]["review_status"] = "open"

    html = render_html(roadmap)
    markdown = render_markdown(roadmap)

    for marker in (
        "learning-console",
        "kg-network-panel",
        "kg-network-node",
        "kg-network-edge",
        "kg-network-canvas",
        "data-kg-reset",
        "data-kg-fit",
        "task-guide-rail",
        "task-progress-checkbox",
        "resource-filter-chip",
        "current-task-filter",
        "data-local-only-filter",
        "bundle-summary-hero",
    ):
        assert marker in html
    for forbidden in (
        "ready-for-evidence",
        "paper-mastery",
        "Explain the problem",
        "score ",
        "chunks=",
        "resources=",
        "retryable=no",
        ">light<",
        ">ev<",
        "бд",
    ):
        assert forbidden not in html
    assert "分数" in html
    assert "片段" in html
    assert "资料数" in html
    assert "轻量检索" in html
    assert 'data-filter-group="download"' in html
    assert 'data-filter-value="downloaded"' in html
    assert 'data-filter-group="type"' in html
    assert 'data-filter-value="paper"' in html
    assert 'data-filter-group="source"' in html
    assert 'data-filter-value="arxiv"' in html
    assert 'data-download="downloaded"' in html
    assert 'data-route="omitted"' in html
    assert 'data-type="repository"' in html
    assert "localStorage" in html
    assert "matchesCurrentTask" in html
    for forbidden in (
        "- mode:",
        "chunks:",
        "resources:",
        "score=",
        "ready-for-evidence",
        "paper-mastery",
        "| explain |",
        "| open |",
    ):
        assert forbidden not in markdown
    assert "检索模式" in markdown
    assert "分数" in markdown
    assert "准备填写证据" in markdown
    assert "论文掌握" in markdown


def test_html_uses_short_display_title_for_long_paper_goal():
    long_title = "Teaching LLMs to Plan: Logical Chain-of-Thought Instruction Tuning for Symbolic Planning"
    roadmap = build_roadmap(
        LearnerProfile(
            goal=f"掌握 {long_title}，能中文汇报、解释关键方法、完成最小复现任务",
            output_language="zh-CN",
            target_kind="paper",
        ),
        [
            Resource(
                title=long_title,
                url="local://paper",
                source="local-library",
                type="paper",
                language="en",
                concepts=["symbolic planning"],
                critical_path_role="core-paper",
                metadata={
                    "target_paper": True,
                    "paper_metadata": {
                        "title": long_title,
                        "abstract_snippet": "Planning paper.",
                        "metadata_status": "local_pdf",
                    },
                },
            )
        ],
    )

    html = render_html(roadmap)

    assert "<h1>Teaching LLMs to Plan 学习路线</h1>" in html
    assert f"<h1>{roadmap['title']}</h1>" not in html


def test_reports_render_full_download_manager_table_for_large_study_bundles():
    roadmap = build_roadmap(
        LearnerProfile(goal="build a practical resource-heavy diffusion study path", output_language="en", target_kind="field"),
        [
            Resource(
                title="Diffusion guide",
                url="https://example.com/diffusion",
                source="course",
                type="article",
                language="en",
                concepts=["diffusion models"],
                estimated_minutes=180,
                trust_score=0.8,
                critical_path_role="focused-support",
            )
        ],
    )
    bundle_resources = []
    for index in range(1, 19):
        status = "failed" if index == 18 else "downloaded"
        bundle_resources.append(
            {
                "index": index,
                "title": f"Long Resource {index} With Enough Words To Require Wrapping In The Download Manager Table",
                "source": "arxiv" if index % 2 else "github",
                "type": "paper" if index % 2 else "repository",
                "status": status,
                "route_status": "selected" if index <= 3 else "omitted",
                "selected": index <= 3,
                "file": f"{index:02d}-long-resource-{index}.pdf" if status != "failed" else "",
                "download_url": f"https://example.com/resource-{index}.pdf",
                "retryable": status == "failed",
                "attempts": 2 if status == "failed" else 1,
                "reason": "temporary network failure" if status == "failed" else "",
            }
        )
    roadmap["study_bundle"] = {
        "manifest_file": "study_bundle_manifest.json",
        "links_file": "links.md",
        "download_manager": {
            "download_queue_file": "download_queue.json",
            "retry_file": "retry_failed.md",
            "completed": 17,
            "retryable": 1,
        },
        "summary": {"downloaded": 17, "failed": 1, "retryable": 1, "completed": 17, "total": 18},
        "policy": "Test bundle policy.",
        "resources": bundle_resources,
    }

    markdown = render_markdown(roadmap)
    html = render_html(roadmap)

    assert "## Download Manager" in markdown
    assert "Long Resource 18" in markdown
    assert "download-manager-panel" in html
    assert "bundle-table-shell" in html
    assert "data-bundle-filter" in html
    assert "download_queue.json" in html
    assert "retry_failed.md" in html
    assert "Long Resource 1 With Enough Words" in html
    assert "Long Resource 18 With Enough Words" in html
    assert ".bundle-table" in html
    assert "table-layout:fixed" in html


def test_download_manager_hides_absent_status_filters_and_labels_reused_files():
    roadmap = {
        "profile": {"output_language": "zh-CN"},
        "study_bundle": {
            "manifest_file": "study_bundle_manifest.json",
            "links_file": "links.md",
            "download_manager": {
                "download_queue_file": "download_queue.json",
                "retry_file": "retry_failed.md",
                "completed": 1,
                "retryable": 0,
            },
            "summary": {"downloaded": 1, "link-only": 0, "failed": 0, "retryable": 0, "completed": 1, "total": 1},
            "policy": "Test bundle policy.",
            "resources": [
                {
                    "index": 1,
                    "title": "Existing Paper",
                    "source": "arxiv",
                    "type": "paper",
                    "status": "downloaded",
                    "route_status": "selected",
                    "selected": True,
                    "file": "01-existing-paper.pdf",
                    "retryable": False,
                    "attempts": 0,
                    "reason": "existing_bundle_file_reused",
                }
            ],
        },
    }

    html = render_html(roadmap)

    assert 'data-bundle-filter="downloaded"' in html
    assert 'data-bundle-filter="link-only"' not in html
    assert 'data-bundle-filter="failed"' not in html
    assert "已复用已有文件" in html
    assert "existing_bundle_file_reused" not in html


def test_planning_paper_route_exposes_books_papers_and_validation_tools():
    profile = LearnerProfile(
        goal="fully master Teaching LLMs to Plan with PDDL symbolic planning PlanBench and logical chain-of-thought",
        output_language="en",
        target_kind="paper",
        route_depth="fastest",
    )
    resources = [
        Resource(
            title="Teaching LLMs to Plan",
            url="local://teaching-llms-to-plan",
            source="local-library",
            type="paper",
            language="en",
            concepts=["large language model", "symbolic planning", "pddl", "chain-of-thought"],
            estimated_minutes=360,
            trust_score=0.8,
            metadata={"target_paper": True},
            critical_path_role="core-paper",
        ),
        Resource(
            title="Automated Planning: Theory and Practice",
            url="https://www.automatedplanning.info/",
            source="book",
            type="book",
            language="en",
            concepts=["automated planning", "symbolic planning"],
            estimated_minutes=720,
            trust_score=0.9,
            critical_path_role="prerequisite",
        ),
        Resource(
            title="PlanBench: On the Planning Abilities of Large Language Models",
            url="https://arxiv.org/abs/2305.15771",
            source="arxiv",
            type="paper",
            language="en",
            concepts=["planbench", "large language model", "pddl"],
            estimated_minutes=240,
            trust_score=0.92,
            critical_path_role="focused-support",
        ),
        Resource(
            title="VAL: The Automatic Validation Tool for PDDL Planning",
            url="https://github.com/KCL-Planning/VAL",
            source="github",
            type="repository",
            language="en",
            concepts=["val verifier", "pddl", "plan validation"],
            estimated_minutes=120,
            trust_score=0.86,
            critical_path_role="practice-validation",
        ),
    ]

    roadmap = build_roadmap(profile, resources)
    selected_titles = [resource["title"] for phase in roadmap["phases"] for resource in phase["resources"]]
    library = roadmap["resource_library"]
    library_titles = {resource["title"] for resource in library}

    assert len(selected_titles) <= 3
    assert "Automated Planning: Theory and Practice" in library_titles
    assert "PlanBench: On the Planning Abilities of Large Language Models" in library_titles
    assert "VAL: The Automatic Validation Tool for PDDL Planning" in library_titles
    assert any(resource["type"] == "book" for resource in library)
    assert any(resource["type"] == "paper" for resource in library)
    assert any(resource["route_status"] == "omitted" for resource in library)


def test_unknown_topic_downgrades_to_resource_discovery_instead_of_fake_mastery_route():
    profile = LearnerProfile(
        goal="learn quantum error correction for a reading group",
        output_language="en",
        target_kind="field",
        route_depth="balanced",
    )
    resources = [
        Resource(
            title="Mathematics for Machine Learning",
            url="https://mml-book.github.io/",
            source="course",
            type="book",
            language="en",
            concepts=["linear algebra", "probability", "optimization"],
            estimated_minutes=720,
            trust_score=0.92,
            critical_path_role="prerequisite",
        )
    ]

    roadmap = build_roadmap(profile, resources)

    assert roadmap["path_strategy"]["readiness"] == "insufficient-evidence"
    assert roadmap["final_artifact"]["type"] == "resource-discovery-plan"
    assert roadmap["artifact_requirements"]["policy"] == "resource-discovery-first"
    assert roadmap["quality_report"]["overall"] == "needs-resources"
    assert roadmap["route_audit"]["coverage_ratio"] == roadmap["route_audit"]["coverage_gate"]["coverage_ratio"]
    assert roadmap["route_audit"]["coverage_ratio"] < roadmap["route_audit"]["coverage_gate"]["threshold"]
    assert "original target-specific candidate resources" in roadmap["route_audit"]["coverage_note"]
    assert roadmap["resource_library"][0]["title"] == "Mathematics for Machine Learning"
    assert any(resource["title"] == "fields-study-flow-resource-discovery-checklist" for resource in roadmap["resource_library"])
    assert {task["type"] for task in roadmap["study_tasks"]} == {"discover", "verify", "regenerate"}
    assert any(gap["status"] == "resource-discovery-required" for gap in roadmap["artifact_gaps"])
    assert any(node["label"] == "Discover target-specific resources" for node in roadmap["mastery_graph"]["nodes"])
    markdown = render_markdown(roadmap)
    html = render_html(roadmap)
    assert "- Coverage: 1.00" not in markdown
    assert "Coverage note" in markdown
    assert "Coverage note" in html


def test_chinese_resource_discovery_route_is_localized():
    profile = LearnerProfile(
        goal="学习量子纠错并能做组会汇报",
        output_language="zh-CN",
        target_kind="field",
        route_depth="balanced",
    )
    resources = [
        Resource(
            title="Mathematics for Machine Learning",
            url="https://mml-book.github.io/",
            source="course",
            type="book",
            language="en",
            concepts=["linear algebra", "probability", "optimization"],
            estimated_minutes=720,
            trust_score=0.92,
            critical_path_role="prerequisite",
        )
    ]

    roadmap = build_roadmap(profile, resources)
    task_titles = [task["title"] for task in roadmap["study_tasks"]]
    task_evidence = [task["evidence"] for task in roadmap["study_tasks"]]
    next_titles = [action["title"] for action in roadmap["next_actions"]]
    checklist = next(resource for resource in roadmap["resource_library"] if resource["title"] == "fields-study-flow-resource-discovery-checklist")

    assert roadmap["path_strategy"]["readiness"] == "insufficient-evidence"
    assert task_titles == ["收集目标相关资料", "验证资料相关性", "重新生成学习路线"]
    assert any("权威论文" in evidence for evidence in task_evidence)
    assert all(title.startswith("从 fields-study-flow-resource-discovery-checklist 开始") for title in next_titles)
    assert checklist["language"] == "zh-CN"
    assert "当前候选资料" in checklist["why_recommended"]


def test_deep_learning_course_gets_books_courses_and_practice_resources():
    profile = LearnerProfile(
        goal="build a deep learning course path from beginner to projects",
        output_language="en",
        target_kind="course",
        route_depth="complete",
        learning_style="practical",
    )
    resources = rank_resources(offline_resources_for_goal(profile.goal), profile)

    roadmap = build_roadmap(profile, resources)
    library_titles = {resource["title"] for resource in roadmap["resource_library"]}
    selected_titles = {resource["title"] for phase in roadmap["phases"] for resource in phase["resources"]}

    assert roadmap["path_strategy"]["readiness"] == "ready"
    assert roadmap["route_audit"]["coverage_ratio"] >= 0.58
    assert "derive" in {task["type"] for task in roadmap["study_tasks"]}
    assert {"explain", "derive", "reproduce", "critique"} <= {task["type"] for task in roadmap["study_tasks"]}
    assert "Dive into Deep Learning" in library_titles
    assert "Deep Learning Book" in library_titles
    assert "PyTorch Tutorials" in library_titles
    assert "Practical Deep Learning for Coders" in library_titles
    assert any(title in selected_titles for title in {"Dive into Deep Learning", "PyTorch Tutorials", "Practical Deep Learning for Coders"})
    assert any(resource["type"] == "book" for resource in roadmap["resource_library"])
    assert any(resource["critical_path_role"] == "practice-validation" for resource in roadmap["resource_library"])
