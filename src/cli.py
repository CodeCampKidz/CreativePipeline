"""Click CLI entry point for the Creative Automation Pipeline."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from slugify import slugify

from src import __version__
from src.service import Pipeline
from src.service.core.logger import get_logger, setup_logging
from src.service.integrations.storage import sync_to_storage
from src.service.pipeline.report import save_report
from src.shared.config import get_settings
from src.shared.exceptions import BriefValidationError, PipelineError
from src.shared.models import BrandConfig, CampaignBrief, PipelineResult

__all__ = ["cli"]

console = Console()


@click.group()
@click.version_option(version=__version__, prog_name="creative-pipeline")
def cli() -> None:
    """Creative Automation Pipeline — Generate social ad campaign creatives with GenAI."""


@cli.command()
@click.argument("brief", type=click.Path(exists=True))
@click.option("--input-dir", "-i", default=None, help="Directory containing existing assets")
@click.option("--output-dir", "-o", default=None, help="Output directory for generated creatives")
@click.option("--brand-config", "-b", default=None, help="Path to brand config YAML file")
@click.option("--dry-run", is_flag=True, help="Validate and show plan without generating")
@click.option("--skip-genai", is_flag=True, help="Skip GenAI, use placeholder images only")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose (DEBUG) console output")
def generate(
    brief: str,
    input_dir: str | None,
    output_dir: str | None,
    brand_config: str | None,
    dry_run: bool,
    skip_genai: bool,
    verbose: bool,
) -> None:
    """Generate campaign creatives from a campaign brief file.

    BRIEF is the path to a YAML or JSON campaign brief file.
    """
    settings = get_settings()

    # Apply CLI overrides
    if input_dir:
        settings.input_assets_dir = input_dir
    if output_dir:
        settings.output_dir = output_dir
    if brand_config:
        settings.brand_config_path = brand_config
    if verbose:
        settings.log_level = "DEBUG"

    setup_logging(settings.log_level)

    # Validate API key (unless skipping GenAI or dry run)
    if not skip_genai and not dry_run and not settings.openai_api_key:
        console.print(
            Panel(
                "[bold red]No OpenAI API key configured.[/bold red]\n\n"
                "Set OPENAI_API_KEY in your .env file, or run with --skip-genai for placeholder mode.\n\n"
                "See .env.example for configuration details.",
                title="Configuration Error",
            )
        )
        sys.exit(1)

    # Load campaign brief
    try:
        campaign_brief = CampaignBrief.from_file(Path(brief))
    except BriefValidationError as exc:
        console.print(f"[bold red]Brief validation error:[/bold red] {exc}")
        if exc.detail:
            console.print(f"  Detail: {exc.detail}")
        sys.exit(1)

    # Load brand config
    brand_cfg = _load_brand_config(Path(settings.brand_config_path))

    # Display campaign summary
    _print_campaign_summary(campaign_brief, dry_run, skip_genai)

    # Run pipeline
    pipeline = Pipeline(settings, campaign_brief, brand_cfg)
    try:
        result = asyncio.run(pipeline.run(dry_run=dry_run, skip_genai=skip_genai))
    except PipelineError as exc:
        console.print(f"[bold red]Pipeline error:[/bold red] {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Pipeline interrupted by user[/yellow]")
        sys.exit(130)

    # Save report to the versioned output directory
    if not dry_run:
        version_dir = (
            Path(settings.output_dir) / slugify(campaign_brief.campaign_name) / f"v{result.version}"
        )
        save_report(result, version_dir)
        sync_to_storage(settings, result)

    _print_results(result, dry_run)


@cli.command()
@click.argument("brief", type=click.Path(exists=True))
def validate(brief: str) -> None:
    """Validate a campaign brief file without generating any assets.

    BRIEF is the path to a YAML or JSON campaign brief file.
    """
    setup_logging("INFO")

    try:
        campaign_brief = CampaignBrief.from_file(Path(brief))
    except BriefValidationError as exc:
        console.print(f"[bold red]Validation failed:[/bold red] {exc}")
        if exc.detail:
            console.print(f"  Detail: {exc.detail}")
        sys.exit(1)

    console.print(
        Panel(
            f"[bold green]Brief is valid![/bold green]\n\n"
            f"Campaign: {campaign_brief.campaign_name}\n"
            f"Products: {len(campaign_brief.products)}\n"
            f"Ratios: {', '.join(r.value for r in campaign_brief.aspect_ratios)}\n"
            f"Languages: {', '.join(campaign_brief.languages)}",
            title="Validation Result",
        )
    )


@cli.command()
@click.option("--host", default=None, help="Bind host (default: 0.0.0.0)")
@click.option("--port", "-p", default=None, type=int, help="Bind port (default: 8080)")
def web(host: str | None, port: int | None) -> None:
    """Launch the web UI for campaign brief upload and creative generation."""
    import uvicorn

    settings = get_settings()
    bind_host = host or settings.web_host
    bind_port = port or settings.web_port

    setup_logging(settings.log_level)
    logger = get_logger("cli")
    logger.info("Starting web UI at http://%s:%d", bind_host, bind_port)

    console.print(
        Panel(
            f"[bold green]Creative Automation Pipeline — Web UI[/bold green]\n\n"
            f"Open your browser to: [bold]http://localhost:{bind_port}[/bold]\n"
            f"Press Ctrl+C to stop.",
            title="Web Server",
        )
    )

    uvicorn.run(
        "src.web.app:app",
        host=bind_host,
        port=bind_port,
        reload=False,
        log_level=settings.log_level.lower(),
    )


def _load_brand_config(path: Path) -> BrandConfig | None:
    """Load brand config if available, return None if not found.

    Args:
        path: Path to brand config YAML.

    Returns:
        BrandConfig or None.
    """
    try:
        return BrandConfig.from_file(path)
    except Exception as exc:
        get_logger("cli").warning("Brand config not loaded: %s — continuing without", exc)
        return None


def _print_campaign_summary(
    brief: CampaignBrief,
    dry_run: bool,
    skip_genai: bool,
) -> None:
    """Print campaign summary to console.

    Args:
        brief: Campaign brief.
        dry_run: Whether running in dry-run mode.
        skip_genai: Whether GenAI is skipped.
    """
    mode = "DRY RUN" if dry_run else ("PLACEHOLDER" if skip_genai else "FULL")
    table = Table(title=f"Campaign: {brief.campaign_name} [{mode}]")
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Products", ", ".join(p.name for p in brief.products))
    table.add_row("Region", brief.target_region)
    table.add_row("Audience", brief.target_audience)
    table.add_row("Message", brief.campaign_message)
    table.add_row("Languages", ", ".join(brief.languages))
    table.add_row("Aspect Ratios", ", ".join(r.value for r in brief.aspect_ratios))
    total = len(brief.products) * len(brief.aspect_ratios) * len(brief.languages)
    table.add_row("Total Creatives", str(total))
    console.print(table)


def _print_results(result: PipelineResult, dry_run: bool) -> None:
    """Print pipeline results summary to console.

    Args:
        result: Pipeline execution result.
        dry_run: Whether running in dry-run mode.
    """
    if dry_run:
        console.print("\n[bold cyan]Dry run complete — no assets generated.[/bold cyan]")
        return

    table = Table(title="Pipeline Results")
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Generated (GenAI)", str(result.total_assets_generated))
    table.add_row("Reused (existing)", str(result.total_assets_reused))
    table.add_row("Placeholders", str(result.total_assets_placeholder))
    table.add_row("Total Time", f"{result.total_time_seconds:.1f}s")

    if result.legal_check:
        status = "[green]PASSED[/green]" if result.legal_check.passed else "[red]FLAGGED[/red]"
        table.add_row("Legal Check", status)

    if result.errors:
        table.add_row("Errors", str(len(result.errors)))

    console.print(table)

    if result.errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for err in result.errors:
            console.print(f"  - {err}")

    # Print output paths
    for pr in result.products:
        for asset in pr.assets:
            console.print(f"  [green]{asset.output_path}[/green]")


# Allow running as: python -m src.cli
if __name__ == "__main__":
    cli()
