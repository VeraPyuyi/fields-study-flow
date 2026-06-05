from __future__ import annotations

from git4study.models import Resource


def offline_resources_for_goal(goal: str) -> list[Resource]:
    lowered = goal.lower()
    resources = _base_catalog()
    if "transformer" in lowered:
        resources.extend(_transformer_catalog())
    if "diffusion" in lowered or "扩散" in goal:
        resources.extend(_diffusion_catalog())
    if "yolo" in lowered:
        resources.extend(_yolo_catalog())
    if "ppo" in lowered or "trpo" in lowered:
        resources.extend(_rl_catalog())
    return resources


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
