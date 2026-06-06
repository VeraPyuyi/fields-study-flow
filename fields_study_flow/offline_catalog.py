from __future__ import annotations

from fields_study_flow.models import Resource


def offline_resources_for_goal(goal: str) -> list[Resource]:
    lowered = goal.lower()
    resources = _base_catalog()
    if _needs_planning_catalog(goal):
        resources.extend(_planning_catalog())
    if _needs_deep_learning_catalog(goal):
        resources.extend(_deep_learning_catalog())
    if "transformer" in lowered:
        resources.extend(_transformer_catalog())
    if "diffusion" in lowered or "扩散" in goal:
        resources.extend(_diffusion_catalog())
    if "yolo" in lowered:
        resources.extend(_yolo_catalog())
    if "ppo" in lowered or "trpo" in lowered:
        resources.extend(_rl_catalog())
    return resources


def _needs_planning_catalog(goal: str) -> bool:
    lowered = goal.lower()
    keywords = (
        "symbolic planning",
        "automated planning",
        "pddl",
        "planning domain definition language",
        "chain-of-thought",
        "chain of thought",
        "logical chain",
        "planbench",
        "val verifier",
        "pddl-instruct",
        "llms to plan",
        "teaching llms to plan",
        "行动规划",
        "符号规划",
        "规划",
    )
    return any(keyword in lowered or keyword in goal for keyword in keywords)


def _needs_deep_learning_catalog(goal: str) -> bool:
    lowered = goal.lower()
    keywords = (
        "deep learning",
        "neural network",
        "neural networks",
        "pytorch",
        "tensorflow",
        "cnn",
        "rnn",
        "深度学习",
        "神经网络",
    )
    return any(keyword in lowered or keyword in goal for keyword in keywords)


def _base_catalog() -> list[Resource]:
    return [
        Resource(
            title="Mathematics for Machine Learning",
            url="https://mml-book.github.io/",
            source="course",
            type="book",
            language="en",
            difficulty="beginner",
            concepts=["linear algebra", "probability", "optimization"],
            estimated_time="12h",
            trust_score=0.92,
            license_or_access_note="Official open book site.",
            metadata={"has_curriculum": True},
        ),
        Resource(
            title="机器学习白板推导",
            url="https://github.com/shuhuai007/Machine-Learning-Session",
            source="github",
            type="repository",
            language="zh-CN",
            difficulty="intermediate",
            concepts=["machine learning", "derivation", "math"],
            estimated_time="10h",
            trust_score=0.78,
            license_or_access_note="Public GitHub repository; check repository license before reuse.",
            metadata={"has_curriculum": True, "has_notebooks": False, "stars": 6000},
        ),
    ]


def _deep_learning_catalog() -> list[Resource]:
    return [
        Resource(
            title="Dive into Deep Learning",
            url="https://d2l.ai/",
            source="book",
            type="book",
            language="en",
            difficulty="beginner",
            concepts=["deep learning", "neural networks", "pytorch", "projects"],
            estimated_time="24h",
            estimated_minutes=1440,
            learning_key_points=[
                "build intuition with executable chapters",
                "connect math, models, and code",
                "complete small end-to-end exercises",
            ],
            focus_areas=["neural networks", "optimization", "cnn", "sequence models"],
            critical_path_role="prerequisite",
            trust_score=0.94,
            why_recommended="Open book with runnable deep-learning examples, useful as the backbone for a course path.",
            license_or_access_note="Official open book site.",
            metadata={"has_curriculum": True, "has_exercises": True, "has_notebooks": True},
        ),
        Resource(
            title="Deep Learning Book",
            url="https://www.deeplearningbook.org/",
            source="book",
            type="book",
            language="en",
            difficulty="advanced",
            concepts=["deep learning", "optimization", "representation learning", "regularization"],
            estimated_time="20h",
            estimated_minutes=1200,
            learning_key_points=[
                "formal foundations for modern deep learning",
                "optimization and regularization principles",
                "representation learning vocabulary",
            ],
            focus_areas=["optimization", "regularization", "representation learning"],
            critical_path_role="focused-support",
            trust_score=0.93,
            why_recommended="Authoritative reference for theory-heavy learners and course synthesis.",
            license_or_access_note="Official book site; use official access terms.",
            metadata={"has_curriculum": True},
        ),
        Resource(
            title="PyTorch Tutorials",
            url="https://pytorch.org/tutorials/",
            source="documentation",
            type="documentation",
            language="en",
            difficulty="beginner",
            concepts=["pytorch", "deep learning", "training loop", "deployment"],
            estimated_time="8h",
            estimated_minutes=480,
            learning_key_points=[
                "run a minimal tensor and autograd example",
                "train a small model end to end",
                "save evidence from a working notebook or script",
            ],
            focus_areas=["PyTorch basics", "training loop", "datasets", "model saving"],
            critical_path_role="practice-validation",
            trust_score=0.92,
            why_recommended="Official hands-on path for turning deep-learning concepts into runnable code.",
            license_or_access_note="Official documentation and tutorial pages.",
            metadata={"has_official_docs": True, "has_exercises": True},
        ),
        Resource(
            title="Practical Deep Learning for Coders",
            url="https://course.fast.ai/",
            source="course",
            type="course",
            language="en",
            difficulty="intermediate",
            concepts=["deep learning", "projects", "computer vision", "nlp"],
            estimated_time="18h",
            estimated_minutes=1080,
            learning_key_points=[
                "learn by building working applications",
                "connect model behavior to project evidence",
                "use notebooks to document experiments",
            ],
            focus_areas=["project workflow", "vision", "nlp", "model iteration"],
            critical_path_role="practice-validation",
            trust_score=0.88,
            why_recommended="Strong project-first course for learners who want practical output.",
            license_or_access_note="Official course site; follow course licensing and platform terms.",
            metadata={"has_curriculum": True, "has_exercises": True, "has_notebooks": True},
        ),
        Resource(
            title="CS231n: Deep Learning for Computer Vision",
            url="https://cs231n.stanford.edu/",
            source="course",
            type="course",
            language="en",
            difficulty="intermediate",
            concepts=["deep learning", "computer vision", "cnn", "assignments"],
            estimated_time="16h",
            estimated_minutes=960,
            learning_key_points=[
                "understand convolutional networks and training practice",
                "work through assignment-style checkpoints",
                "connect visual models to evaluation and failure modes",
            ],
            focus_areas=["CNNs", "training", "vision assignments", "evaluation"],
            critical_path_role="focused-support",
            trust_score=0.9,
            why_recommended="Recognized course material for a structured deep-learning curriculum.",
            license_or_access_note="Public course page; follow official course terms.",
            metadata={"has_curriculum": True, "has_exercises": True},
        ),
    ]


def _planning_catalog() -> list[Resource]:
    return [
        Resource(
            title="Automated Planning: Theory and Practice",
            url="https://www.automatedplanning.info/",
            source="book",
            type="book",
            language="en",
            difficulty="intermediate",
            concepts=["automated planning", "symbolic planning", "state space search", "heuristics"],
            estimated_time="12h",
            estimated_minutes=720,
            learning_key_points=[
                "planning task formalization",
                "state-space and plan-space search",
                "heuristics used by classical planners",
            ],
            focus_areas=["planning problems", "actions", "preconditions", "heuristics"],
            critical_path_role="prerequisite",
            trust_score=0.9,
            why_recommended="Gives the compact classical planning background needed to understand PDDL-style symbolic planning papers.",
            license_or_access_note="Book/reference site. Use official pages or library access; do not download from unauthorized mirrors.",
            metadata={"has_curriculum": True},
        ),
        Resource(
            title="PDDL Reference",
            url="https://planning.wiki/ref/pddl",
            source="documentation",
            type="documentation",
            language="en",
            difficulty="beginner",
            concepts=["pddl", "planning domain definition language", "preconditions", "effects"],
            estimated_time="90min",
            estimated_minutes=90,
            learning_key_points=[
                "domain and problem files",
                "action preconditions and effects",
                "goal validity in symbolic planning",
            ],
            focus_areas=["PDDL syntax", "domain file", "problem file", "action model"],
            critical_path_role="focused-support",
            trust_score=0.82,
            why_recommended="A short reference that directly unlocks the PDDL terminology used throughout the target paper.",
            license_or_access_note="Public reference page; link and summarize.",
            metadata={"has_official_docs": False, "has_curriculum": True},
        ),
        Resource(
            title="PlanBench: On the Planning Abilities of Large Language Models",
            url="https://arxiv.org/abs/2305.15771",
            source="arxiv",
            type="paper",
            language="en",
            difficulty="advanced",
            concepts=["planbench", "large language model", "symbolic planning", "pddl"],
            estimated_time="4h",
            estimated_minutes=240,
            learning_key_points=[
                "benchmark tasks for LLM planning",
                "failure modes in planning evaluation",
                "how formal validators expose invalid plans",
            ],
            focus_areas=["PlanBench", "LLM planning evaluation", "PDDL tasks", "validity checks"],
            critical_path_role="focused-support",
            trust_score=0.92,
            why_recommended="Provides the key benchmark context for understanding why instruction-tuned logical CoT is being evaluated.",
            license_or_access_note="arXiv abstract and PDF link.",
            metadata={"has_official_docs": True},
        ),
        Resource(
            title="Chain-of-Thought Prompting Elicits Reasoning in Large Language Models",
            url="https://arxiv.org/abs/2201.11903",
            source="arxiv",
            type="paper",
            language="en",
            difficulty="intermediate",
            concepts=["chain-of-thought", "large language model", "reasoning"],
            estimated_time="3h",
            estimated_minutes=180,
            learning_key_points=[
                "why intermediate reasoning steps matter",
                "prompted reasoning versus fine-tuned reasoning",
                "limits of CoT as evidence of correctness",
            ],
            focus_areas=["CoT rationale", "reasoning traces", "LLM evaluation"],
            critical_path_role="focused-support",
            trust_score=0.94,
            why_recommended="Clarifies the reasoning technique that the target paper adapts into logical planning traces.",
            license_or_access_note="arXiv abstract and PDF link.",
        ),
        Resource(
            title="VAL: The Automatic Validation Tool for PDDL Planning",
            url="https://github.com/KCL-Planning/VAL",
            source="github",
            type="repository",
            language="en",
            difficulty="intermediate",
            concepts=["val verifier", "pddl", "plan validation", "symbolic planning"],
            estimated_time="2h",
            estimated_minutes=120,
            learning_key_points=[
                "validate whether generated plans satisfy PDDL constraints",
                "connect paper claims to executable checking",
                "record validation errors as reproduction evidence",
            ],
            focus_areas=["VAL", "plan validity", "PDDL validation", "experiment evidence"],
            critical_path_role="practice-validation",
            trust_score=0.86,
            why_recommended="Gives a concrete validation tool for the paper's plan-validity and feedback-loop discussion.",
            license_or_access_note="Public GitHub repository; check repository license before reuse.",
            metadata={"has_notebooks": False, "has_curriculum": False},
        ),
    ]


def _transformer_catalog() -> list[Resource]:
    return [
        Resource(
            title="The Illustrated Transformer",
            url="https://jalammar.github.io/illustrated-transformer/",
            source="course",
            type="article",
            language="en",
            difficulty="beginner",
            concepts=["transformer", "attention", "sequence modeling"],
            estimated_time="2h",
            trust_score=0.86,
            license_or_access_note="Public article page; link and summarize only.",
            metadata={"has_curriculum": True},
        ),
        Resource(
            title="Attention Is All You Need",
            url="https://arxiv.org/abs/1706.03762",
            source="arxiv",
            type="paper",
            language="en",
            difficulty="advanced",
            concepts=["transformer", "self attention", "positional encoding"],
            estimated_time="6h",
            trust_score=0.97,
            license_or_access_note="arXiv abstract and PDF link.",
            metadata={"has_official_docs": True},
        ),
        Resource(
            title="Transformers from Scratch",
            url="https://github.com/karpathy/nanoGPT",
            source="github",
            type="repository",
            language="en",
            difficulty="intermediate",
            concepts=["transformer", "language model", "python"],
            estimated_time="8h",
            trust_score=0.9,
            license_or_access_note="Public GitHub repository; check license before reuse.",
            metadata={"has_curriculum": True, "has_notebooks": False, "stars": 40000, "recently_updated": True},
        ),
    ]


def _diffusion_catalog() -> list[Resource]:
    return [
        Resource(
            title="Diffusion Models Beat GANs on Image Synthesis",
            url="https://arxiv.org/abs/2105.05233",
            source="arxiv",
            type="paper",
            language="en",
            difficulty="advanced",
            concepts=["diffusion models", "score matching", "image synthesis"],
            estimated_time="5h",
            trust_score=0.93,
            license_or_access_note="arXiv abstract and PDF link.",
        ),
        Resource(
            title="扩散模型 Diffusion Model 综述与教程",
            url="https://www.bilibili.com/",
            source="bilibili",
            type="video",
            language="zh-CN",
            difficulty="intermediate",
            concepts=["diffusion models", "score matching"],
            estimated_time="3h",
            trust_score=0.7,
            license_or_access_note="Link-level recommendation; use official platform page.",
        ),
    ]


def _yolo_catalog() -> list[Resource]:
    return [
        Resource(
            title="Ultralytics YOLO Docs",
            url="https://docs.ultralytics.com/",
            source="course",
            type="documentation",
            language="en",
            difficulty="beginner",
            concepts=["yolo", "object detection", "cnn"],
            estimated_time="4h",
            trust_score=0.88,
            license_or_access_note="Official documentation.",
            metadata={"has_official_docs": True, "has_curriculum": True},
        ),
        Resource(
            title="YOLOv5 repository",
            url="https://github.com/ultralytics/yolov5",
            source="github",
            type="repository",
            language="en",
            difficulty="intermediate",
            concepts=["yolo", "object detection", "training"],
            estimated_time="10h",
            trust_score=0.86,
            license_or_access_note="Public GitHub repository; check license before reuse.",
            metadata={"has_notebooks": True, "stars": 50000, "recently_updated": True},
        ),
    ]


def _rl_catalog() -> list[Resource]:
    return [
        Resource(
            title="Spinning Up in Deep RL",
            url="https://spinningup.openai.com/",
            source="course",
            type="course",
            language="en",
            difficulty="intermediate",
            concepts=["ppo", "trpo", "policy gradient", "reinforcement learning"],
            estimated_time="15h",
            trust_score=0.9,
            license_or_access_note="Official educational site.",
            metadata={"has_curriculum": True, "has_exercises": True},
        ),
        Resource(
            title="Proximal Policy Optimization Algorithms",
            url="https://arxiv.org/abs/1707.06347",
            source="arxiv",
            type="paper",
            language="en",
            difficulty="advanced",
            concepts=["ppo", "policy gradient", "reinforcement learning"],
            estimated_time="5h",
            trust_score=0.95,
            license_or_access_note="arXiv abstract and PDF link.",
        ),
    ]
