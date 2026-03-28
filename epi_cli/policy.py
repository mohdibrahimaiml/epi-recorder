"""
epi policy - Create, validate, and inspect epi_policy.json rule files.

This command is the policy front door for non-technical reviewers. It helps
teams create a company rulebook without having to hand-author JSON, while
keeping epi_policy.json as the machine-readable storage format.
"""

import json
import shutil
import zipfile
from datetime import date
from json import JSONDecodeError
from pathlib import Path
from typing import Optional

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax
from rich.table import Table
from typer.models import OptionInfo

from epi_cli.view import _cleanup_after_delay, _make_temp_dir, _open_in_browser
from epi_core.container import _html_safe_json_dumps
from epi_core.policy import (
    EPIPolicy,
    POLICY_PROFILES,
    build_policy_from_profile,
    build_starter_policy,
    list_policy_profiles,
    list_starter_rule_types,
)

app = typer.Typer(help="Manage epi_policy.json for fault analysis rules.")
console = Console()

POLICY_FILENAME = "epi_policy.json"

GUIDED_PROFILE_CHOICES = {
    "finance-approval": {
        "label": "Finance approvals and underwriting",
        "profile": "finance.loan-underwriting",
        "description": "For high-value approvals, lending, and underwriting decisions.",
    },
    "finance-refund": {
        "label": "Finance refunds and payments",
        "profile": "finance.refund-agent",
        "description": "For refunds, reimbursements, and payment operations.",
    },
    "healthcare-triage": {
        "label": "Healthcare triage",
        "profile": "healthcare.triage",
        "description": "For clinical triage and escalation decisions.",
    },
    "healthcare-assistant": {
        "label": "Clinical assistant",
        "profile": "healthcare.clinical-assistant",
        "description": "For clinical support with signoff and safety controls.",
    },
    "custom-starter": {
        "label": "Custom starter policy",
        "profile": None,
        "description": "Start from a small generic rulebook and customize it yourself.",
    },
}

STARTER_RULE_PROMPTS = (
    ("threshold_guard", "Should high-value actions require human approval?", "threshold"),
    ("approval_guard", "Should sensitive named actions require explicit reviewer approval?", None),
    ("sequence_guard", "Should one step be required before another?", None),
    ("constraint_guard", "Should the workflow stay within known numeric limits?", None),
    ("prohibition_guard", "Should secret-like strings be blocked from output?", None),
    ("tool_permission_guard", "Should only approved tools be allowed?", None),
)


def _resolve_option_value(value, default):
    return default if isinstance(value, OptionInfo) else value


def _build_policy_editor_case_payload(policy_data: dict, output_path: Path) -> dict:
    scope = policy_data.get("scope") or {}
    workflow_name = scope.get("workflow") or policy_data.get("system_name") or output_path.stem
    policy_version = str(policy_data.get("policy_version") or date.today())

    return {
        "source_name": output_path.name,
        "file_size": output_path.stat().st_size if output_path.exists() else 0,
        "manifest": {
            "system_name": policy_data.get("system_name") or output_path.stem,
            "system_version": policy_data.get("system_version") or "1.0",
            "workflow_name": workflow_name,
            "workflow_id": policy_data.get("policy_id") or output_path.stem,
            "created_at": f"{policy_version}T00:00:00Z",
            "goal": "Define the rulebook for this workflow.",
            "notes": "Local browser policy editor session created by epi policy init.",
        },
        "steps": [
            {
                "kind": "session.start",
                "timestamp": f"{policy_version}T00:00:00Z",
                "content": {
                    "workflow": workflow_name,
                    "mode": "policy-editor",
                },
            }
        ],
        "analysis": {
            "summary": "Drafting the rulebook for this workflow.",
            "primary_findings": [],
            "secondary_flags": [],
        },
        "policy": policy_data,
        "policy_evaluation": None,
        "review": None,
        "environment": {
            "mode": "policy-editor",
            "source": "epi policy init",
        },
        "integrity": {
            "ok": True,
            "checked": 0,
            "mismatches": [],
        },
        "signature": {
            "valid": False,
            "reason": "Local policy editor workspace",
        },
    }


def _create_policy_editor_html(policy_data: dict, output_path: Path) -> str:
    web_viewer_dir = Path(__file__).resolve().parents[1] / "web_viewer"
    template_path = web_viewer_dir / "index.html"
    app_js_path = web_viewer_dir / "app.js"
    css_path = web_viewer_dir / "styles.css"
    crypto_js_path = Path(__file__).resolve().parents[1] / "epi_viewer_static" / "crypto.js"

    template_html = template_path.read_text(encoding="utf-8")
    app_js = app_js_path.read_text(encoding="utf-8")
    css_styles = css_path.read_text(encoding="utf-8")
    crypto_js = crypto_js_path.read_text(encoding="utf-8")

    payload = {
        "cases": [_build_policy_editor_case_payload(policy_data, output_path)],
        "ui": {"view": "rules"},
    }
    payload_json = _html_safe_json_dumps(payload, indent=2)
    preload_tag = f'<script id="epi-preloaded-cases" type="application/json">{payload_json}</script>'

    html = template_html.replace(
        '<link rel="stylesheet" href="styles.css">',
        f"<style>{css_styles}</style>",
    )
    html = html.replace(
        '<script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>\n<script src="../epi_viewer_static/crypto.js"></script>\n<script src="app.js"></script>',
        f'{preload_tag}\n<script src="https://cdn.jsdelivr.net/npm/jszip@3.10.1/dist/jszip.min.js"></script>\n<script>{crypto_js}</script>\n<script>{app_js}</script>',
    )
    return html


def _open_policy_editor(policy_data: dict, output_path: Path) -> Path:
    temp_dir = _make_temp_dir()
    if temp_dir is None:
        raise RuntimeError("Could not create a temporary browser workspace.")

    try:
        viewer_path = temp_dir / "policy_editor.html"
        viewer_path.write_text(_create_policy_editor_html(policy_data, output_path), encoding="utf-8")
        _open_in_browser(viewer_path)
        _cleanup_after_delay(temp_dir, 30.0)
        return viewer_path
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def _policy_summary_table(policy: EPIPolicy) -> Table:
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Rule", style="cyan", no_wrap=True)
    table.add_column("What it means")
    table.add_column("Severity", no_wrap=True)

    severity_colors = {
        "critical": "red",
        "high": "yellow",
        "medium": "blue",
        "low": "dim",
    }

    for rule in policy.rules:
        color = severity_colors.get(rule.severity, "white")
        table.add_row(
            rule.id,
            rule.description,
            f"[{color}]{rule.severity}[/{color}]",
        )
    return table


def _print_policy_summary(policy: EPIPolicy, output_path: Optional[Path | str] = None) -> None:
    profile_label = getattr(policy, "profile_id", None) or "custom"
    where = f"\nStored at: [bold]{output_path}[/bold]" if output_path else ""
    scope_bits = []
    if policy.scope:
        for key in ("organization", "team", "application", "workflow", "environment"):
            value = getattr(policy.scope, key, None)
            if value:
                scope_bits.append(f"{key}={value}")
    console.print(
        Panel(
            (
                "EPI stores the company rulebook as [cyan]epi_policy.json[/cyan]. "
                "Most users should not edit JSON manually."
                f"{where}"
            ),
            title="Policy Summary",
        )
    )
    console.print(f"[bold]System:[/bold] {policy.system_name} v{policy.system_version}")
    console.print(f"[bold]Policy version:[/bold] {policy.policy_version}")
    if policy.policy_id:
        console.print(f"[bold]Policy ID:[/bold] {policy.policy_id}")
    if scope_bits:
        console.print(f"[bold]Scope:[/bold] {', '.join(scope_bits)}")
    console.print(f"[bold]Profile:[/bold] {profile_label}")
    console.print(f"[bold]Rules enabled:[/bold] {len(policy.rules)}\n")
    if policy.rules:
        console.print(_policy_summary_table(policy))
        console.print()


def _load_policy_payload(path: Path) -> tuple[dict, str]:
    """
    Load policy JSON from either a standalone policy file or an .epi artifact.

    Returns:
        tuple: (policy_payload, source_label)
    """
    if path.suffix.lower() == ".epi":
        if not path.exists():
            raise FileNotFoundError(path)
        if not zipfile.is_zipfile(path):
            raise ValueError(f"Not a valid .epi file: {path}")
        with zipfile.ZipFile(path, "r") as zf:
            if "policy.json" not in zf.namelist():
                raise FileNotFoundError(f"No embedded policy.json found in {path.name}")
            return json.loads(zf.read("policy.json").decode("utf-8")), f"{path} (embedded policy)"

    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8")), str(path)


def _print_policy_validation_failure(path: Path, exc: Exception) -> None:
    if isinstance(exc, JSONDecodeError):
        console.print(f"[red][FAIL][/red] Invalid JSON in [bold]{path}[/bold]")
        console.print("[bold]Could not parse policy file[/bold]")
        console.print(
            Panel(
                f"{exc.msg}\nLine {exc.lineno}, column {exc.colno}",
                title="Could not parse policy file",
            )
        )
        return

    if isinstance(exc, ValidationError):
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Field", style="cyan", no_wrap=True)
        table.add_column("Problem")
        for error in exc.errors():
            location = ".".join(str(part) for part in error.get("loc", []) if part is not None) or "<root>"
            message = error.get("msg", "Invalid value")
            table.add_row(location, message)

        console.print(f"[red][FAIL][/red] Policy schema is invalid: [bold]{path}[/bold]")
        console.print("[bold]Validation Errors[/bold]")
        console.print(
            Panel(
                "Fix the fields below, then run [bold]epi policy validate[/bold] again.",
                title="Validation Errors",
            )
        )
        console.print(table)
        return

    console.print(f"[red][FAIL][/red] Invalid policy: {exc}")


def _remove_rule(policy: dict, rule_id: str) -> None:
    policy["rules"] = [rule for rule in policy["rules"] if rule["id"] != rule_id]


def _get_rule(policy: dict, rule_id: str) -> Optional[dict]:
    for rule in policy["rules"]:
        if rule["id"] == rule_id:
            return rule
    return None


def _customize_profile_policy(policy: dict, profile_name: str, yes: bool) -> dict:
    if profile_name == "finance.loan-underwriting":
        if yes or Confirm.ask("Should high-value approvals require human approval?", default=True):
            threshold = "10000" if yes else Prompt.ask(
                "Approval threshold amount",
                default=str(int(_get_rule(policy, "R003")["threshold_value"])),
            )
            rule = _get_rule(policy, "R003")
            if rule is not None:
                rule["threshold_value"] = float(threshold)
        else:
            _remove_rule(policy, "R003")

        if not (yes or Confirm.ask("Should secret-like tokens be blocked from output?", default=True)):
            _remove_rule(policy, "R004")

        if not (yes or Confirm.ask("Should risk checks happen before approval?", default=True)):
            _remove_rule(policy, "R002")

    elif profile_name == "finance.refund-agent":
        if not (yes or Confirm.ask("Must identity verification happen before refunds?", default=True)):
            _remove_rule(policy, "R002")

        if yes or Confirm.ask("Should large refunds require human approval?", default=True):
            threshold = "5000" if yes else Prompt.ask(
                "Refund threshold amount",
                default=str(int(_get_rule(policy, "R003")["threshold_value"])),
            )
            rule = _get_rule(policy, "R003")
            if rule is not None:
                rule["threshold_value"] = float(threshold)
        else:
            _remove_rule(policy, "R003")

        if not (yes or Confirm.ask("Should secret-like payment tokens be blocked from output?", default=True)):
            _remove_rule(policy, "R004")

    elif profile_name == "healthcare.triage":
        if not (yes or Confirm.ask("Should triage decisions require symptom capture first?", default=True)):
            _remove_rule(policy, "R002")

        if yes or Confirm.ask("Should high-risk cases require clinician escalation?", default=True):
            threshold = "8" if yes else Prompt.ask(
                "Clinical risk threshold",
                default=str(int(_get_rule(policy, "R003")["threshold_value"])),
            )
            rule = _get_rule(policy, "R003")
            if rule is not None:
                rule["threshold_value"] = float(threshold)
        else:
            _remove_rule(policy, "R003")

        if not (yes or Confirm.ask("Should secret-like tokens be blocked from output?", default=True)):
            _remove_rule(policy, "R004")

    elif profile_name == "healthcare.clinical-assistant":
        if not (yes or Confirm.ask("Should patient context be required before recommendations?", default=True)):
            _remove_rule(policy, "R002")

        if yes or Confirm.ask("Should severe cases require clinician signoff?", default=True):
            threshold = "7" if yes else Prompt.ask(
                "Severity score threshold",
                default=str(int(_get_rule(policy, "R003")["threshold_value"])),
            )
            rule = _get_rule(policy, "R003")
            if rule is not None:
                rule["threshold_value"] = float(threshold)
        else:
            _remove_rule(policy, "R003")

        if not (yes or Confirm.ask("Should secret-like values be blocked from output?", default=True)):
            _remove_rule(policy, "R004")

    return policy


def _build_custom_starter_policy(
    system_name: str,
    system_version: str,
    policy_version: str,
    yes: bool,
    starter_rule_types: Optional[list[str]] = None,
) -> dict:
    if starter_rule_types:
        return build_starter_policy(
            system_name=system_name,
            system_version=system_version,
            policy_version=policy_version,
            rule_types=starter_rule_types,
            profile_id="custom.guided",
        )

    selected_rule_types: list[str] = []
    for rule_type, question, _kind in STARTER_RULE_PROMPTS:
        if yes or Confirm.ask(question, default=rule_type in {"threshold_guard", "approval_guard", "prohibition_guard"}):
            selected_rule_types.append(rule_type)

    return build_starter_policy(
        system_name=system_name,
        system_version=system_version,
        policy_version=policy_version,
        rule_types=selected_rule_types,
        profile_id="custom.guided",
    )


@app.command("init")
def init(
    output: str = typer.Option(POLICY_FILENAME, "--output", "-o", help="Output path for the policy file"),
    profile: Optional[str] = typer.Option(
        None,
        "--profile",
        help="Built-in policy profile, e.g. finance.loan-underwriting or healthcare.triage",
    ),
    starter_rule: Optional[list[str]] = typer.Option(
        None,
        "--starter-rule",
        help="Starter rule type for the custom starter path. Repeat to include multiple rule types.",
    ),
    open_editor: bool = typer.Option(
        False,
        "--open-editor",
        help="Open the browser Rules editor with this policy preloaded after writing the file.",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Accept all defaults without prompting"),
):
    """
    Create an epi_policy.json rulebook.

    By default this runs a guided setup flow for non-technical reviewers.
    """
    output = _resolve_option_value(output, POLICY_FILENAME)
    profile = _resolve_option_value(profile, None)
    starter_rule = _resolve_option_value(starter_rule, []) or []
    open_editor = _resolve_option_value(open_editor, False)
    yes = _resolve_option_value(yes, False)
    output_path = Path(output)
    if output_path.exists() and not yes:
        if not Confirm.ask(f"[yellow]{output_path}[/yellow] already exists. Overwrite?", default=False):
            raise typer.Exit(0)

    console.print("\n[bold]Guided EPI Policy Setup[/bold]\n")
    console.print(
        "Policy is the company rulebook for this workflow. "
        "EPI records the run, checks it against that rulebook, and embeds both into the artifact.\n"
    )
    console.print(
        "[dim]EPI stores the company rulebook as epi_policy.json; most users should not edit JSON manually.[/dim]\n"
    )

    policy_version = str(date.today())

    available_starter_rules = set(list_starter_rule_types())
    invalid_starter_rules = [rule for rule in starter_rule if rule not in available_starter_rules]
    if invalid_starter_rules:
        console.print(f"[red][FAIL][/red] Unknown starter rule type(s): {', '.join(invalid_starter_rules)}")
        console.print(f"[dim]Available starter rules: {', '.join(sorted(available_starter_rules))}[/dim]")
        raise typer.Exit(1)

    if profile and starter_rule:
        console.print("[red][FAIL][/red] --starter-rule can only be used with the custom starter path.")
        raise typer.Exit(1)

    if yes and not profile and not starter_rule:
        profile = "finance.loan-underwriting"

    if not yes and not profile and not starter_rule:
        table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
        table.add_column("Choice", style="cyan", no_wrap=True)
        table.add_column("Workflow")
        table.add_column("Use this when...")
        for choice, config in GUIDED_PROFILE_CHOICES.items():
            table.add_row(choice, config["label"], config["description"])
        console.print(table)
        console.print()
        choice = Prompt.ask("Workflow type", default="finance-approval")
        while choice not in GUIDED_PROFILE_CHOICES:
            console.print("[red][FAIL][/red] Unknown choice. Pick one of the listed workflow types.")
            choice = Prompt.ask("Workflow type", default="finance-approval")
        profile = GUIDED_PROFILE_CHOICES[choice]["profile"]
    elif profile and profile not in POLICY_PROFILES:
        available = ", ".join(list_policy_profiles())
        console.print(f"[red][FAIL][/red] Unknown profile: [bold]{profile}[/bold]")
        console.print(f"[dim]Available profiles: {available}[/dim]")
        raise typer.Exit(1)

    default_system_name = "my-ai-system" if not profile else profile.split(".")[-1]
    system_name = default_system_name if yes else Prompt.ask("System name", default=default_system_name)
    system_version = "1.0" if yes else Prompt.ask("System version", default="1.0")

    if profile:
        policy_data = build_policy_from_profile(
            profile,
            system_name=system_name,
            system_version=system_version,
            policy_version=policy_version,
        )
        policy_data = _customize_profile_policy(policy_data, profile, yes=yes)
    else:
        policy_data = _build_custom_starter_policy(
            system_name,
            system_version,
            policy_version,
            yes=yes,
            starter_rule_types=list(starter_rule),
        )

    output_path.write_text(json.dumps(policy_data, indent=2), encoding="utf-8")
    policy = EPIPolicy(**policy_data)

    console.print(f"\n[green][OK][/green] Policy written to [bold]{output_path}[/bold]\n")
    _print_policy_summary(policy, output_path=output_path)
    if open_editor:
        try:
            editor_path = _open_policy_editor(policy_data, output_path)
            console.print(f"[green][OK][/green] Opened browser policy editor: [bold]{editor_path}[/bold]\n")
        except Exception as exc:
            console.print(
                "[yellow][WARN][/yellow] Policy file was created, but the browser policy editor could not be opened: "
                f"{exc}\n"
            )
    else:
        console.print(
            "[dim]Tip:[/dim] Add [bold]--open-editor[/bold] to continue in the browser Rules editor next time.\n"
        )
    console.print("[dim]Next steps:[/dim]")
    console.print("  1. Run your instrumented workflow with EPI")
    console.print("  2. Open the resulting .epi file")
    console.print("  3. Review the rulebook and any flagged fault together\n")


@app.command("profiles")
def profiles():
    """List built-in healthcare and finance policy profiles."""
    table = Table(show_header=True, header_style="bold", box=None, padding=(0, 2))
    table.add_column("Profile", style="cyan", no_wrap=True)
    table.add_column("Description")

    for name in list_policy_profiles():
        table.add_row(name, POLICY_PROFILES[name]["description"])

    console.print()
    console.print(
        Panel(
            "Built-in policy packs for high-risk healthcare and finance workflows.",
            title="EPI Policy Profiles",
        )
    )
    console.print(table)
    console.print()


@app.command("validate")
def validate(
    policy_file: str = typer.Argument(POLICY_FILENAME, help="Path to policy file"),
):
    """Validate an epi_policy.json file and show a summary."""
    path = Path(policy_file)
    try:
        data, source_label = _load_policy_payload(path)
        policy = EPIPolicy(**data)
    except FileNotFoundError as exc:
        console.print(f"[red][X] File not found:[/red] {exc}")
        raise typer.Exit(1)
    except Exception as exc:
        _print_policy_validation_failure(path, exc)
        raise typer.Exit(1)

    console.print(f"\n[green][OK][/green] Valid policy: [bold]{source_label}[/bold]\n")
    _print_policy_summary(policy, output_path=source_label)


@app.command("show")
def show(
    policy_file: str = typer.Argument(POLICY_FILENAME, help="Path to policy file"),
    raw: bool = typer.Option(False, "--raw", help="Also print the raw JSON after the human-readable summary."),
    open_editor: bool = typer.Option(
        False,
        "--open-editor",
        help="Open the browser Rules editor with this policy preloaded.",
    ),
):
    """Show a reviewer-friendly summary of a policy file or embedded artifact policy."""
    raw = _resolve_option_value(raw, False)
    open_editor = _resolve_option_value(open_editor, False)
    path = Path(policy_file)
    try:
        data, source_label = _load_policy_payload(path)
    except FileNotFoundError as exc:
        console.print(f"[red][X] Not found:[/red] {exc}")
        raise typer.Exit(1)
    except ValueError as exc:
        console.print(f"[red][X] {exc}[/red]")
        raise typer.Exit(1)
    except KeyError:
        console.print(f"[red][X] No embedded policy found in:[/red] {path}")
        raise typer.Exit(1)
    except Exception as exc:
        console.print(f"[red][FAIL] Could not read policy:[/red] {exc}")
        raise typer.Exit(1)

    try:
        policy = EPIPolicy(**data)
    except Exception as exc:
        console.print(f"[red][FAIL] Invalid policy data:[/red] {exc}")
        raise typer.Exit(1)

    if path.suffix.lower() == ".epi":
        console.print(f"[dim]Showing embedded policy from:[/dim] {path}")

    _print_policy_summary(policy, output_path=source_label)

    if open_editor:
        try:
            editor_path = _open_policy_editor(data, path)
            console.print(f"[green][OK][/green] Opened browser policy editor: [bold]{editor_path}[/bold]\n")
        except Exception as exc:
            console.print(
                "[yellow][WARN][/yellow] Policy summary was shown, but the browser policy editor could not be opened: "
                f"{exc}\n"
            )

    if raw:
        console.print(
            Panel(
                "Raw JSON is shown below for advanced editing and debugging.",
                title="Raw Policy JSON",
            )
        )
        console.print(Syntax(json.dumps(data, indent=2), "json", theme="monokai"))
