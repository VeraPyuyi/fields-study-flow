from fields_study_flow.live_search import search_live_resources


class FakeResponse:
    def __init__(self, *, text: str = "", data: dict | None = None, status_code: int = 200):
        self.text = text
        self._data = data or {}
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status {self.status_code}")

    def json(self) -> dict:
        return self._data


class FakeClient:
    def __init__(self):
        self.urls: list[str] = []

    def get(self, url: str, **_kwargs) -> FakeResponse:
        self.urls.append(url)
        if "export.arxiv.org" in url:
            return FakeResponse(
                text="""<?xml version="1.0" encoding="UTF-8"?>
                <feed xmlns="http://www.w3.org/2005/Atom">
                  <entry>
                    <id>https://arxiv.org/abs/1706.03762</id>
                    <title>Attention Is All You Need</title>
                    <summary>Transformer self-attention sequence transduction.</summary>
                  </entry>
                </feed>"""
            )
        if "api.github.com" in url:
            return FakeResponse(
                data={
                    "items": [
                        {
                            "full_name": "example/transformer-repro",
                            "html_url": "https://github.com/example/transformer-repro",
                            "description": "Transformer reproduction notebook",
                            "stargazers_count": 1200,
                            "updated_at": "2026-01-01T00:00:00Z",
                        }
                    ]
                }
            )
        if "api.openalex.org" in url:
            return FakeResponse(
                data={
                    "results": [
                        {
                            "display_name": "Instant Neural Graphics Primitives with a Multiresolution Hash Encoding",
                            "id": "https://openalex.org/W999",
                            "cited_by_count": 5000,
                            "concepts": [{"display_name": "Computer graphics"}, {"display_name": "Rendering"}],
                        },
                        {
                            "display_name": "How Does ChatGPT Perform on the United States Medical Licensing Examination?",
                            "id": "https://openalex.org/W998",
                            "cited_by_count": 1500,
                            "concepts": [{"display_name": "Large language model"}, {"display_name": "Medical education"}],
                        },
                        {
                            "display_name": "Attention Is All You Need",
                            "id": "https://openalex.org/W170603762",
                            "cited_by_count": 100000,
                            "concepts": [{"display_name": "Artificial intelligence"}],
                        },
                    ]
                }
            )
        return FakeResponse(data={})


def test_search_live_resources_uses_open_sources_and_skips_credentialed_sources():
    client = FakeClient()

    resources, diagnostics = search_live_resources(
        "master Transformer paper",
        sources=["arxiv", "github", "youtube"],
        language_preference="en-first",
        client=client,
    )

    assert {resource.source for resource in resources} == {"arxiv", "github"}
    assert "youtube" in diagnostics["manual_link_only_sources"]
    assert not any("youtube" in url for url in client.urls)
    assert any(resource.metadata.get("live_search") for resource in resources)


def test_search_live_resources_filters_off_target_openalex_papers():
    client = FakeClient()

    resources, diagnostics = search_live_resources(
        "master Transformer paper",
        sources=["openalex"],
        language_preference="en-first",
        client=client,
    )

    titles = {resource.title for resource in resources}
    assert diagnostics["status"] == "ok"
    assert "Attention Is All You Need" in titles
    assert "Instant Neural Graphics Primitives with a Multiresolution Hash Encoding" not in titles
    assert "How Does ChatGPT Perform on the United States Medical Licensing Examination?" not in titles
