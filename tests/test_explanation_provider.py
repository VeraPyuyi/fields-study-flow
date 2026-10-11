import copy
import json

import httpx
import pytest

from fields_study_flow import explanation_provider as transport
from fields_study_flow.explanations import prepare_explanations


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    for name in ("ENABLED", "BASE_URL", "MODEL", "API_KEY"):
        monkeypatch.delenv("FIELDS_STUDY_FLOW_LLM_" + name, raising=False)


@pytest.fixture
def configured(monkeypatch):
    for name, value in {"ENABLED": "true", "BASE_URL": "https://example.invalid/v1",
                        "MODEL": "user-model", "API_KEY": "private-test-key"}.items():
        monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_" + name, value)


@pytest.fixture
def context():
    return {"schema_version": 1, "snapshot_id": "v1", "bundle_id": "bundle",
        "sources": [{"id": "s", "fingerprint": "f1"}],
        "anchors": [{"id": "a", "source_id": "s", "snippet": "The method uses 8 heads.",
                     "locator": {"page": 2}, "locator_status": "valid"}],
        "claims": [{"id": "c", "kind": "methodology", "anchor_ids": ["a"], "statement": "Method"}]}


def good_response():
    return {"items": [{"claim_id": "c", "plain_meaning": "The method uses 8 heads.",
                       "why_it_matters": "Compare the heads with the input tokens.", "anchor_ids": ["a"]}]}


def mock_http(monkeypatch, handler):
    real_client = httpx.Client
    def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["timeout"].connect is not None
        assert kwargs["timeout"].read is not None
        return real_client(transport=httpx.MockTransport(handler), **kwargs)
    monkeypatch.setattr(transport.httpx, "Client", client)
    monkeypatch.setattr(transport.time, "sleep", lambda _delay: None)


def test_http_chat_completions_success(context, configured, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        assert str(request.url) == "https://example.invalid/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer private-test-key"
        payload = json.loads(request.content)
        assert payload["model"] == "user-model"
        assert payload["stream"] is False
        assert "private-test-key" not in request.content.decode()
        assert len(payload["messages"]) == 2
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(good_response())}}]})
    mock_http(monkeypatch, handler)
    result = prepare_explanations(context)
    assert result["mode"] == "llm" and result["status"] == "ready"
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["invalid_json", "timeout", "429", "500", "401", "bad_envelope"])
def test_http_failure_falls_back_with_bounded_retries_and_no_leaks(context, configured, monkeypatch, caplog, failure):
    calls = []
    def handler(request):
        calls.append(request)
        if failure == "timeout":
            raise httpx.ReadTimeout("private-test-key response secret", request=request)
        if failure in {"429", "500", "401"}:
            return httpx.Response(int(failure), text="private-test-key private response")
        if failure == "bad_envelope":
            return httpx.Response(200, json={"secret": "private-test-key"})
        return httpx.Response(200, json={"choices": [{"message": {"content": "not JSON private-test-key"}}]})
    mock_http(monkeypatch, handler)
    result = prepare_explanations(context)
    assert result["mode"] == "local" and result["status"] == "fallback"
    assert result["warnings"]
    assert len(calls) == (3 if failure in {"timeout", "429", "500"} else 1)
    assert "private-test-key" not in json.dumps(result)
    assert "private response" not in caplog.text
    assert "private-test-key" not in caplog.text


def test_429_then_success_retries(context, configured, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "999999"})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(good_response())}}]})
    mock_http(monkeypatch, handler)
    assert prepare_explanations(context)["mode"] == "llm"
    assert len(calls) == 2


@pytest.mark.parametrize("mode,offline", [("auto", True), ("llm", True), ("local", False)])
def test_offline_and_local_have_zero_requests_even_with_config(context, configured, monkeypatch, mode, offline):
    def forbidden(**_kwargs):
        pytest.fail("must not construct an HTTP client")
    monkeypatch.setattr(transport.httpx, "Client", forbidden)
    result = prepare_explanations(context, provider_mode=mode, offline=offline,
                                  provider=lambda _p: pytest.fail("must not call provider"))
    assert result["mode"] == "local"


@pytest.mark.parametrize("enabled", [None, "false", "1", "yes", "TRUEish"])
def test_keys_without_explicit_true_do_not_enable_auto(context, configured, monkeypatch, enabled):
    if enabled is None:
        monkeypatch.delenv("FIELDS_STUDY_FLOW_LLM_ENABLED")
    else:
        monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_ENABLED", enabled)
    result = prepare_explanations(context, provider=lambda _p: pytest.fail("auto must remain local"))
    assert result["mode"] == "local"


@pytest.mark.parametrize("missing", ["ENABLED", "BASE_URL", "MODEL", "API_KEY"])
def test_explicit_llm_configuration_error_precedes_generation(context, configured, monkeypatch, missing):
    monkeypatch.delenv("FIELDS_STUDY_FLOW_LLM_" + missing)
    with pytest.raises(ValueError, match="FIELDS_STUDY_FLOW_LLM_" + missing):
        prepare_explanations(context, provider_mode="llm", provider=lambda _p: pytest.fail("generation ran"))


@pytest.mark.parametrize("url", ["not a URL", "ftp://example.invalid", "https://user:private-test-key@example.invalid", "https://example.invalid?key=private-test-key"])
def test_bad_endpoint_rejected_without_echoing_credentials(context, configured, monkeypatch, url):
    monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_BASE_URL", url)
    with pytest.raises(ValueError) as error:
        prepare_explanations(context, provider_mode="llm")
    assert "private-test-key" not in str(error.value)


def test_cache_hit_and_invalidation(context, configured, tmp_path, monkeypatch):
    calls = []
    def provider(_payload):
        calls.append(True)
        return good_response()
    first = prepare_explanations(context, cache_dir=tmp_path, provider=provider)
    assert prepare_explanations(context, cache_dir=tmp_path, provider=provider) == first
    assert len(calls) == 1
    for mutate in (
        lambda c: c.update(snapshot_id="v2"),
        lambda c: c["sources"][0].update(fingerprint="f2"),
        lambda c: c["anchors"][0].update(snippet="The method uses 8 heads and compares tokens."),
    ):
        changed = copy.deepcopy(context)
        mutate(changed)
        assert prepare_explanations(changed, cache_dir=tmp_path, provider=provider)["mode"] == "llm"
    prepare_explanations(context, language="en", cache_dir=tmp_path, provider=provider)
    monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_MODEL", "another-model")
    prepare_explanations(context, cache_dir=tmp_path, provider=provider)
    monkeypatch.setattr(transport, "PROMPT_VERSION", "next-prompt")
    prepare_explanations(context, cache_dir=tmp_path, provider=provider)
    assert len(calls) == 7
    assert "private-test-key" not in "".join(p.read_text() for p in tmp_path.glob("*.json"))
    assert prepare_explanations(context, offline=True, cache_dir=tmp_path, provider=provider)["mode"] == "local"
    assert len(calls) == 7


def test_cache_revalidated_corruption_and_failed_calls_not_cached(context, configured, tmp_path):
    calls = []
    def provider(_payload):
        calls.append(True)
        return good_response()
    prepare_explanations(context, cache_dir=tmp_path, provider=provider)
    cache = next(tmp_path.glob("*.json"))
    cache.write_text('{"items": []}', encoding="utf-8")
    assert prepare_explanations(context, cache_dir=tmp_path, provider=provider)["mode"] == "llm"
    assert len(calls) == 2
    other = tmp_path / "failed"
    def failure(_payload):
        raise RuntimeError("private-test-key")
    assert prepare_explanations(context, cache_dir=other, provider=failure)["status"] == "fallback"
    assert not list(other.glob("*.json"))
    assert prepare_explanations(context, cache_dir=other, provider=provider)["mode"] == "llm"


def test_invalid_mode_and_language_raise(context):
    with pytest.raises(ValueError):
        prepare_explanations(context, provider_mode="anything")
    with pytest.raises(ValueError):
        prepare_explanations(context, language="not-supported")


def test_cache_tampered_numbers_revalidated(context, configured, tmp_path):
    calls = []
    def provider(_payload):
        calls.append(True)
        return good_response()
    prepare_explanations(context, cache_dir=tmp_path, provider=provider)
    cache = next(tmp_path.glob("*.json"))
    tampered = good_response()
    tampered["items"][0]["plain_meaning"] = "Fabricated 999 heads."
    cache.write_text(json.dumps(tampered), encoding="utf-8")
    result = prepare_explanations(context, cache_dir=tmp_path, provider=provider)
    assert len(calls) == 2 and "999" not in result["items"][0]["plain_meaning"]


def test_cache_io_failure_keeps_valid_result(context, configured, tmp_path):
    file = tmp_path / "not-a-directory"
    file.write_text("occupied", encoding="utf-8")
    result = prepare_explanations(context, cache_dir=file, provider=lambda _p: good_response())
    assert result["mode"] == "llm" and result["warnings"] == ["cache_write_failed"]


@pytest.mark.parametrize("raw", ["[]", '{"items": [], "items": []}', '{"items": NaN}', '```json\n{}\n```'])
def test_strict_json_rejects_duplicates_constants_and_fences(context, configured, raw):
    assert prepare_explanations(context, provider=lambda _p: raw)["status"] == "fallback"


def test_redirect_never_followed(context, configured, monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(302, headers={"Location": "https://another.invalid/collect"})
    mock_http(monkeypatch, handler)
    assert prepare_explanations(context)["status"] == "fallback"
    assert len(calls) == 1


def test_oversized_http_response_rejected(context, configured, monkeypatch):
    def handler(_request):
        return httpx.Response(200, text="x" * (transport.MAX_RESPONSE_BYTES + 1))
    mock_http(monkeypatch, handler)
    assert prepare_explanations(context)["warnings"] == ["provider_response_rejected"]


def test_configuration_repr_does_not_expose_key(configured):
    config = transport.resolve_config()
    assert "private-test-key" not in repr(config)
    assert "example.invalid" not in repr(config)


def test_api_key_in_endpoint_path_rejected_before_http(context, configured, monkeypatch):
    monkeypatch.setenv("FIELDS_STUDY_FLOW_LLM_BASE_URL", "https://example.invalid/private-test-key/v1")
    with pytest.raises(ValueError) as error:
        prepare_explanations(context, provider=lambda _p: good_response())
    assert "private-test-key" not in str(error.value)


def test_auto_explicitly_enabled_but_incomplete_is_actionable(context, configured, monkeypatch):
    monkeypatch.delenv("FIELDS_STUDY_FLOW_LLM_MODEL")
    with pytest.raises(ValueError, match="FIELDS_STUDY_FLOW_LLM_MODEL"):
        prepare_explanations(context, provider=lambda _p: pytest.fail("configuration was not checked"))
