"""发布说明的运行回归与工作流门禁的静态契约。"""

import re
import runpy
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
SCRIPT = ROOT / "build" / "release_notes.py"


def workflow(name):
    return (WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8")


def job(source, name):
    return re.search(rf"^  {name}:\n(.*?)(?=^  [\w-]+:|\Z)", source, re.M | re.S)[1]


def step(source, name):
    return re.search(rf"      - name: {name}\n(.*?)(?=      - |\Z)", source, re.S)[1]


def test_ci_is_reusable_and_checks_all_required_commands():
    source = workflow("ci")
    assert "  workflow_call:" in source
    assert "ruff check src tests build/release_notes.py" in job(source, "lint")
    assert "ruff format --check src tests build/release_notes.py" in job(source, "lint")
    assert "build/verify_web_downloads.py" in step(source, "Ruff check")
    assert "build/verify_web_downloads.py" in step(source, "Ruff format check")
    assert 'python-version: ["3.10", "3.12", "3.14"]' in job(source, "test")
    assert "pytest -q" in job(source, "test")
    assert "continue-on-error:" not in source


@pytest.mark.parametrize(
    "name,downstream", [("release", "build-windows-portable"), ("pages", "deploy")]
)
def test_build_and_deploy_require_same_commit_quality(name, downstream):
    source = workflow(name)
    assert "uses: ./.github/workflows/ci.yml" in job(source, "quality")
    assert "needs: quality" in job(source, downstream)
    assert "always()" not in source
    assert "continue-on-error:" not in source
    assert "ref:" not in source  # checkout 默认使用触发提交，不能改为 main。


def test_release_tag_guard_and_windows_gui_tests_remain_enabled():
    source = workflow("release")
    guard = step(source, "Verify version matches tag")
    assert "if: github.ref_type == 'tag'" in guard
    assert "actual != expected" in guard
    assert 'THESISLINT_RUN_GUI_TESTS: "1"' in step(source, "Run tests")


def test_packaged_cli_is_checked_before_the_release_archive_is_created():
    source = workflow("release")
    verification = step(source, "Verify portable executable")
    assert "python build/verify_portable.py --executable dist/thesislint.exe" in verification
    assert "$LASTEXITCODE -ne 0" in verification
    assert "throw" in verification
    assert source.index("Build single-file executable") < source.index("Verify portable executable")
    assert source.index("Verify portable executable") < source.index("Package portable zip")
    assert "if:" not in verification  # 标签发布与手动干跑都检查真实程序。
    assert "build/verify_portable.py" in step(workflow("ci"), "Ruff check")
    assert "build/verify_portable.py" in step(workflow("ci"), "Ruff format check")


def test_release_dispatch_is_dry_run_even_when_a_tag_is_selected():
    source = workflow("release")
    release = step(source, "Create GitHub Release")
    assert "if: github.event_name == 'push' && github.ref_type == 'tag'" in release
    assert "if: github.event_name == 'workflow_dispatch'" in step(source, "Upload dry-run artifact")


def test_pages_paths_include_shared_checks_and_keep_manual_deployment():
    source = workflow("pages")
    assert '".github/workflows/ci.yml"' in source
    assert '"tests/**"' in source
    assert '"build/release_notes.py"' in source
    assert "  workflow_dispatch:" in source
    assert "if:" not in step(source, "Deploy to GitHub Pages")


def test_release_calls_version_notes_script_before_publishing():
    source = workflow("release")
    notes = step(source, "Write release notes")
    assert "python build/release_notes.py" in notes
    assert '--tag "${GITHUB_REF_NAME}"' in notes
    assert '--sha256 "${SHA256}"' in notes
    assert '--zipname "${ZIPNAME}"' in notes
    assert "--notes-file release_notes.md" in step(source, "Create GitHub Release")
    assert "/blob/main/CHANGELOG.md" not in source


@pytest.fixture
def extract():
    return runpy.run_path(str(SCRIPT))["extract_version_section"]


@pytest.mark.parametrize("newline", ["\n", "\r\n"])
def test_version_notes_keep_only_exact_version_section(extract, newline):
    changelog = newline.join(
        [
            "# 更新日志",
            "## 未发布",
            "- 待发布内容",
            "## v1.20.0",
            "- 其他版",
            "## v1.2.0",
            "",
            "本版概述。",
            "",
            "### 修复",
            "- 本版修复",
            "",
            "## v1.1.0",
            "- 旧版",
        ]
    )
    assert extract(changelog, "v1.2.0") == "本版概述。\n\n### 修复\n- 本版修复"


@pytest.mark.parametrize("marker", ["`", "~"])
@pytest.mark.parametrize("opening_length,closing_length", [(3, 3), (4, 5)])
@pytest.mark.parametrize("indent", ["", "   "])
def test_version_notes_preserve_fenced_headings(
    extract, marker, opening_length, closing_length, indent
):
    other_marker = "~" if marker == "`" else "`"
    section = "\n".join(
        [
            "- 本版修复之前",
            indent + marker * opening_length + "markdown",
            "## v1.2.0",
            marker * (opening_length - 1),
            "## 短围栏不能关闭",
            other_marker * opening_length,
            "## 不同符号不能关闭",
            marker * opening_length + " 仍然是内容",
            "## 带内容的围栏不能关闭",
            indent + marker * closing_length + "\t",
            "- 本版修复之后",
        ]
    )
    changelog = "\n".join(
        [
            "## 未发布",
            marker * 3,
            "## v1.2.0",
            marker * 3,
            "## v1.2.0",
            section,
            "## v1.1.0",
            "- 旧版",
        ]
    )
    assert extract(changelog, "v1.2.0") == section


@pytest.mark.parametrize("marker", ["`", "~"])
def test_fenced_version_heading_does_not_satisfy_required_section(extract, marker):
    changelog = "\n".join(["## 未发布", marker * 3, "## v1.2.0", "- 示例", marker * 3])
    with pytest.raises(ValueError, match="exactly one"):
        extract(changelog, "v1.2.0")


@pytest.mark.parametrize(
    "changelog",
    [
        "## 未发布\n- 新功能",
        "## v1.2.0\n\n## v1.1.0\n- 旧版",
        "## v1.2.0\n- 第一段\n## v1.2.0\n- 第二段",
    ],
)
def test_missing_empty_or_duplicate_version_notes_fail(extract, changelog):
    with pytest.raises(ValueError):
        extract(changelog, "v1.2.0")


def test_script_generates_download_details_and_tag_pinned_link(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("## 未发布\n- 尚未发布\n\n## v1.2.0\n\n- 本版修复\n", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--tag",
            "v1.2.0",
            "--sha256",
            "a" * 64,
            "--zipname",
            "portable.zip",
            "--repository",
            "owner/repo",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode == 0, result.stderr
    notes = (tmp_path / "release_notes.md").read_text(encoding="utf-8")
    assert "- 本版修复" in notes
    assert "尚未发布" not in notes
    assert "Windows 10+ x64" in notes
    assert "黑白双主题" in notes
    assert "程序未签名" in notes
    assert f"{'a' * 64} *portable.zip" in notes
    assert "https://github.com/owner/repo/blob/v1.2.0/CHANGELOG.md" in notes


def test_missing_changelog_version_fails_without_output(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text("## v0.7.0\n- 旧版", encoding="utf-8")
    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--tag",
            "v1.2.0",
            "--sha256",
            "a" * 64,
            "--zipname",
            "portable.zip",
            "--repository",
            "owner/repo",
        ],
        cwd=tmp_path,
        capture_output=True,
        check=False,
    )
    assert result.returncode != 0
    assert not (tmp_path / "release_notes.md").exists()
