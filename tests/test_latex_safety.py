from types import SimpleNamespace

import pytest

from fields_study_flow.paper_lens import _compile_latex


@pytest.mark.parametrize("engine", ["xelatex", "lualatex", "pdflatex", "tectonic"])
def test_report_compiler_disables_shell_and_remote_bundle_fetches(tmp_path, monkeypatch, engine):
    tex = tmp_path / "paper_lens.tex"
    tex.write_text("source", encoding="utf-8")
    calls = []

    def run(command, **kwargs):
        calls.append(command)
        tex.with_suffix(".pdf").write_bytes(b"fixture")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("fields_study_flow.paper_lens.subprocess.run", run)
    assert _compile_latex(tex, engine)["compile_status"] == "compiled"
    if engine == "tectonic":
        assert "--only-cached" in calls[0] and "--untrusted" in calls[0]
    else:
        assert "-no-shell-escape" in calls[0]
