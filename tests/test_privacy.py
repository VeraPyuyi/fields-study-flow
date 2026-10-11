import pytest

from fields_study_flow.models import Resource
from fields_study_flow.roadmap import sanitize_roadmap_for_export


@pytest.mark.parametrize("path", [r"\\server\share\private\paper.pdf", "/mnt/research/paper.pdf", "/srv/private/model.py", "/research/unpublished/paper.pdf", "C:/Users/example/private/paper.pdf"])
def test_public_views_redact_private_paths(path):
    assert path not in str(sanitize_roadmap_for_export({"notes": path}))
    assert path not in str(Resource(title="Paper", url="", source="local", type="paper", metadata={"notes": path}).to_dict())


@pytest.mark.parametrize("value", ["../../study-assets/paper.pdf", "https://example.org/data/paper.pdf", "/training/learning_rate", "dataset/scores.csv"])
def test_portable_links_urls_and_json_locators_survive(value):
    assert sanitize_roadmap_for_export({"value": value})["value"] == value
