from fields_study_flow.mcp_tools import searchResources, validateSources


def test_search_resources_applies_hard_language_filter_at_tool_boundary():
    result = searchResources("diffusion", languagePreference="zh-only")

    assert result["resources"]
    assert all(resource["language"] == "zh-CN" for resource in result["resources"])


def test_validate_sources_rejects_piracy_bypass_and_download_instructions():
    plan = {
        "phases": [
            {
                "resources": [
                    {
                        "title": "pirate",
                        "url": "https://sci-hub.example/paper",
                        "license_or_access_note": "mirror",
                    },
                    {
                        "title": "download video",
                        "url": "https://youtube.com/watch?v=abc",
                        "license_or_access_note": "download video with a helper tool",
                    },
                    {
                        "title": "bypass",
                        "url": "https://example.com/course",
                        "license_or_access_note": "bypass login and copy full text",
                    },
                ]
            }
        ]
    }

    result = validateSources(plan)

    assert result["valid"] is False
    assert any("Disallowed source" in issue for issue in result["issues"])
    assert any("download video" in issue for issue in result["issues"])
    assert any("bypass login" in issue for issue in result["issues"])
