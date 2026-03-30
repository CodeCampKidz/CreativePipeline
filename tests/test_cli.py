"""Tests for CLI interface using Click CliRunner."""

from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from src.cli import cli


class TestCliValidate:
    """Tests for the validate command."""

    def test_validate_valid_brief(self, sample_brief_yaml: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(sample_brief_yaml)])
        assert result.exit_code == 0
        assert "valid" in result.output.lower()

    def test_validate_nonexistent_file(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", "/nonexistent/brief.yaml"])
        assert result.exit_code != 0

    def test_validate_invalid_brief(self, tmp_path: Path) -> None:
        bad_brief = tmp_path / "bad.yaml"
        bad_brief.write_text("campaign_name: test\nproducts: []")
        runner = CliRunner()
        result = runner.invoke(cli, ["validate", str(bad_brief)])
        assert result.exit_code != 0


class TestCliGenerate:
    """Tests for the generate command."""

    def test_generate_dry_run(self, sample_brief_yaml: Path, tmp_path: Path) -> None:
        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "generate",
                str(sample_brief_yaml),
                "--dry-run",
                "--output-dir",
                str(tmp_path / "output"),
            ],
        )
        assert result.exit_code == 0
        assert "dry run" in result.output.lower() or "DRY RUN" in result.output

    def test_generate_no_api_key_no_skip_exits(self, sample_brief_yaml: Path) -> None:
        runner = CliRunner(env={"OPENAI_API_KEY": "", "STORAGE_BACKEND": "local"})
        result = runner.invoke(
            cli,
            ["generate", str(sample_brief_yaml)],
        )
        assert result.exit_code != 0
        assert "API key" in result.output or "Configuration" in result.output

    def test_generate_skip_genai(self, sample_brief_yaml: Path, tmp_path: Path) -> None:
        output_dir = tmp_path / "output"
        runner = CliRunner(env={"OPENAI_API_KEY": "", "STORAGE_BACKEND": "local"})
        result = runner.invoke(
            cli,
            [
                "generate",
                str(sample_brief_yaml),
                "--skip-genai",
                "--output-dir",
                str(output_dir),
            ],
        )
        assert result.exit_code == 0

    def test_generate_nonexistent_brief(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["generate", "/nonexistent/brief.yaml"])
        assert result.exit_code != 0

    def test_version_flag(self) -> None:
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "1.0.0" in result.output
