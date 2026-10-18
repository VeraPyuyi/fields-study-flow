from fields_study_flow.mcp_tools import searchResources, validateSources, ingestUrl, buildRoadmap


def test_imported_safe_notes_and_parsed_host_validation():
    for url in ['HTTPS://ARXIV.ORG/abs/1706.03762?utm_source=a', 'https://example.org/?next=sci-hub']:
        resource = ingestUrl(url)
        plan = buildRoadmap('paper', {}, [resource])
        assert validateSources(plan)['valid']
    safe = {'title': 'safe', 'url': 'https://example.org', 'license_or_access_note': 'do not bypass login; do not copy long copyrighted passages; do not download video'}
    assert validateSources({'phases': [{'resources': [safe]}]})['valid']


def test_structured_access_policy_rejects_unsafe_operations():
    for policy in [{'action': 'download_video'}, {'action': 'hotlink'}, {'bypass_login': True}, {'authorized': False}, {'mirror': True}]:
        resource = ingestUrl('https://example.org/open')
        resource['metadata']['access_policy'] = policy
        assert not validateSources({'phases': [{'resources': [resource]}]})['valid']
    for url in ['https://SCI-HUB.example/p?utm_source=x', 'ftp://example.org/a', 'https://user:password@example.org/a']:
        resource = {'url': url, 'title': 'bad', 'license_or_access_note': 'link'}
        assert not validateSources({'phases': [{'resources': [resource]}]})['valid']


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
