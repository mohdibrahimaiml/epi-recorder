#requires -Version 5.1

param(
    [string]$Python = ".\.venv\Scripts\python.exe",
    [string]$WorkspaceRoot = "",
    [switch]$KeepWorkspace
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$repoRoot = Split-Path -Parent $PSScriptRoot
$runId = Get-Date -Format "yyyyMMdd_HHmmss"

if ([string]::IsNullOrWhiteSpace($WorkspaceRoot)) {
    # Default to a repo-local clean room so the script stays automation-safe
    # in restricted environments. Pass -WorkspaceRoot to point elsewhere.
    $WorkspaceRoot = Join-Path $repoRoot ".tmp\AGTEPI\$runId"
}

$workspaceRoot = [System.IO.Path]::GetFullPath($WorkspaceRoot)
$distDir = Join-Path $workspaceRoot "dist"
$inputsDir = Join-Path $workspaceRoot "inputs"
$outputsDir = Join-Path $workspaceRoot "outputs"
$reportsDir = Join-Path $workspaceRoot "reports"
$buildTemp = Join-Path $workspaceRoot "build-temp"
$runtimeTemp = Join-Path $workspaceRoot "runtime-temp"
$userHome = Join-Path $workspaceRoot "user-home"
$venvDir = Join-Path $workspaceRoot ".venv"
$checklistSource = Join-Path $PSScriptRoot "validate_agt_userflow_checklist.md"
$checklistDest = Join-Path $reportsDir "manual_view_checklist.md"
$reportPath = Join-Path $reportsDir "validation_report.md"

$script:Failures = New-Object System.Collections.Generic.List[string]
$script:ScenarioResults = New-Object System.Collections.Generic.List[object]
$script:InstallChecks = [ordered]@{}
$script:CurrentPhase = "initializing"
$script:EnvironmentSummary = [ordered]@{
    started_at = (Get-Date).ToString("u")
    repo_root = $repoRoot
    workspace_root = $workspaceRoot
}

Add-Type -AssemblyName System.IO.Compression.FileSystem

function Resolve-PythonCommand([string]$PythonValue) {
    if (Test-Path $PythonValue) {
        return (Resolve-Path $PythonValue).Path
    }

    $cmd = Get-Command $PythonValue -ErrorAction SilentlyContinue
    if ($cmd) {
        return $cmd.Source
    }

    throw "Python not found at '$PythonValue'. Pass -Python explicitly."
}

function Resolve-BasePythonCommand([string]$PythonCmd) {
    $result = Invoke-ExternalCommand -FilePath $PythonCmd -Arguments @(
        "-c",
        "import sys; print(getattr(sys, '_base_executable', sys.executable))"
    ) -WorkingDirectory $repoRoot -Environment @{}
    if ($result.ExitCode -ne 0) {
        return $PythonCmd
    }

    $candidate = ($result.Output -split "`r?`n" | Select-Object -Last 1).Trim()
    if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path $candidate)) {
        return $candidate
    }
    return $PythonCmd
}

function Ensure-Directory([string]$Path) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Quote-CommandPart([string]$Value) {
    if ($null -eq $Value) {
        return '""'
    }
    if ($Value -match '[\s"]') {
        return '"' + ($Value -replace '"', '\"') + '"'
    }
    return $Value
}

function Format-Command([string]$FilePath, [string[]]$Arguments) {
    $parts = @($FilePath) + $Arguments
    return ($parts | ForEach-Object { Quote-CommandPart $_ }) -join " "
}

function Invoke-ExternalCommand {
    param(
        [Parameter(Mandatory = $true)][string]$FilePath,
        [string[]]$Arguments = @(),
        [Parameter(Mandatory = $true)][string]$WorkingDirectory,
        [hashtable]$Environment = @{}
    )

    $savedEnv = @{}
    foreach ($key in $Environment.Keys) {
        $savedEnv[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$Environment[$key], "Process")
    }

    Push-Location $WorkingDirectory
    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $FilePath @Arguments 2>&1 | Out-String
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
        Pop-Location
        foreach ($key in $Environment.Keys) {
            [Environment]::SetEnvironmentVariable($key, $savedEnv[$key], "Process")
        }
    }

    return [pscustomobject]@{
        Command = Format-Command $FilePath $Arguments
        ExitCode = $exitCode
        Output = ($output.TrimEnd())
    }
}

function Test-PythonTempWrite([string]$PythonExecutable, [string]$ProbeTempDir) {
    Ensure-Directory $ProbeTempDir
    $probeFile = Join-Path $ProbeTempDir "temp-write-probe.py"
    $probeScript = @'
import pathlib
import tempfile

with tempfile.TemporaryDirectory() as d:
    path = pathlib.Path(d) / "input.json"
    path.write_text('{"ok": true}', encoding="utf-8")
    print(path)
'@

    Set-Content -Path $probeFile -Value $probeScript -Encoding UTF8
    try {
        cmd /d /c "`"$PythonExecutable`" `"$probeFile`" >nul 2>nul" | Out-Null
        return $LASTEXITCODE -eq 0
    }
    finally {
        Remove-Item -Path $probeFile -Force -ErrorAction SilentlyContinue
    }
}

function Write-PythonTempShim([string]$ShimDir, [string]$SafeTempDir) {
    Ensure-Directory $ShimDir
    Ensure-Directory $SafeTempDir

    $siteCustomize = @"
import os
import pathlib
import shutil
import tempfile
import uuid

_SAFE_BASE = pathlib.Path(r"$SafeTempDir")
_SAFE_BASE.mkdir(parents=True, exist_ok=True)

def _manual_mkdtemp(suffix=None, prefix=None, dir=None):
    base = pathlib.Path(dir) if dir else _SAFE_BASE
    base.mkdir(parents=True, exist_ok=True)
    name = f"{prefix or 'tmp'}{uuid.uuid4().hex}{suffix or ''}"
    path = base / name
    path.mkdir(parents=True, exist_ok=False)
    return str(path)

class _ManualTemporaryDirectory:
    def __init__(self, suffix=None, prefix=None, dir=None, ignore_cleanup_errors=False):
        self.name = _manual_mkdtemp(suffix=suffix, prefix=prefix, dir=dir)
        self._ignore_cleanup_errors = ignore_cleanup_errors

    def __enter__(self):
        return self.name

    def __exit__(self, exc_type, exc, tb):
        self.cleanup()
        return False

    def cleanup(self):
        shutil.rmtree(self.name, ignore_errors=self._ignore_cleanup_errors)

tempfile.mkdtemp = _manual_mkdtemp
tempfile.TemporaryDirectory = _ManualTemporaryDirectory
tempfile.tempdir = str(_SAFE_BASE)
os.environ["TMP"] = str(_SAFE_BASE)
os.environ["TEMP"] = str(_SAFE_BASE)
"@

    Set-Content -Path (Join-Path $ShimDir "sitecustomize.py") -Value $siteCustomize -Encoding UTF8
}

function Build-ManualWheel([string]$PythonCmd) {
    $builderPath = Join-Path $workspaceRoot "manual_wheel_builder.py"
    $builderScript = @"
from __future__ import annotations

import base64
import csv
import hashlib
import pathlib
import tomllib
import zipfile

repo_root = pathlib.Path(r"$repoRoot")
dist_dir = pathlib.Path(r"$distDir")
dist_dir.mkdir(parents=True, exist_ok=True)

pyproject = tomllib.loads((repo_root / "pyproject.toml").read_text(encoding="utf-8"))
project = pyproject["project"]
name = project["name"]
version = project["version"]
summary = project.get("description", "")
requires_python = project.get("requires-python", "")
normalized = name.replace("-", "_")
wheel_name = f"{normalized}-{version}-py3-none-any.whl"
wheel_path = dist_dir / wheel_name
dist_info = f"{normalized}-{version}.dist-info"

package_roots = [
    "epi_core",
    "epi_cli",
    "epi_gateway",
    "epi_recorder",
    "epi_analyzer",
    "epi_viewer_static",
    "web_viewer",
    "pytest_epi",
]
single_files = ["epi_postinstall.py"]
skip_parts = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".git"}
skip_suffixes = {".pyc", ".pyo"}


def should_include(path: pathlib.Path) -> bool:
    if not path.is_file():
        return False
    if any(part in skip_parts for part in path.parts):
        return False
    if path.suffix.lower() in skip_suffixes:
        return False
    return True


def record_digest(data: bytes) -> tuple[str, str]:
    digest = hashlib.sha256(data).digest()
    encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return f"sha256={encoded}", str(len(data))


records: list[tuple[str, str, str]] = []

metadata_lines = [
    "Metadata-Version: 2.1",
    f"Name: {name}",
    f"Version: {version}",
]
if summary:
    metadata_lines.append(f"Summary: {summary}")
if requires_python:
    metadata_lines.append(f"Requires-Python: {requires_python}")
for requirement in project.get("dependencies", []):
    metadata_lines.append(f"Requires-Dist: {requirement}")
metadata_content = ("\n".join(metadata_lines) + "\n").encode("utf-8")

wheel_content = (
    "Wheel-Version: 1.0\n"
    "Generator: validate_agt_userflow.ps1 (manual-wheel-fallback)\n"
    "Root-Is-Purelib: true\n"
    "Tag: py3-none-any\n"
).encode("utf-8")

entry_points_lines = ["[console_scripts]"]
for script_name, entrypoint in project.get("scripts", {}).items():
    entry_points_lines.append(f"{script_name} = {entrypoint}")
entry_points_content = ("\n".join(entry_points_lines) + "\n").encode("utf-8")

top_level_content = ("\n".join(package_roots) + "\n").encode("utf-8")

file_paths: list[pathlib.Path] = []
for root_name in package_roots:
    root_path = repo_root / root_name
    if root_path.exists():
        file_paths.extend(path for path in root_path.rglob("*") if should_include(path))
for file_name in single_files:
    file_path = repo_root / file_name
    if should_include(file_path):
        file_paths.append(file_path)

with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for source_path in sorted(file_paths):
        arcname = source_path.relative_to(repo_root).as_posix()
        data = source_path.read_bytes()
        zf.writestr(arcname, data)
        digest, size = record_digest(data)
        records.append((arcname, digest, size))

    generated_members = {
        f"{dist_info}/METADATA": metadata_content,
        f"{dist_info}/WHEEL": wheel_content,
        f"{dist_info}/entry_points.txt": entry_points_content,
        f"{dist_info}/top_level.txt": top_level_content,
    }
    for arcname, data in generated_members.items():
        zf.writestr(arcname, data)
        digest, size = record_digest(data)
        records.append((arcname, digest, size))

    record_name = f"{dist_info}/RECORD"
    record_rows = records + [(record_name, "", "")]
    record_buffer = []
    for row in record_rows:
        record_buffer.append(",".join(row))
    record_content = ("\n".join(record_buffer) + "\n").encode("utf-8")
    zf.writestr(record_name, record_content)

print(wheel_path)
"@

    Set-Content -Path $builderPath -Value $builderScript -Encoding UTF8
    $result = Invoke-ExternalCommand -FilePath $PythonCmd -Arguments @($builderPath) -WorkingDirectory $repoRoot -Environment @{
        TMP = $buildTemp
        TEMP = $buildTemp
    }
    if ($result.ExitCode -ne 0) {
        throw "Manual wheel builder failed.`n$($result.Output)"
    }

    $wheelPath = ($result.Output -split "`r?`n" | Select-Object -Last 1).Trim()
    if (-not (Test-Path $wheelPath)) {
        throw "Manual wheel builder did not produce a wheel artifact."
    }
    return $wheelPath
}

function Build-ValidationWheel([string]$PythonCmd) {
    $script:CurrentPhase = "building wheel: preparing directories"
    Ensure-Directory $distDir
    Ensure-Directory $buildTemp

    if (Test-Path (Join-Path $repoRoot "build")) {
        Remove-Item -Recurse -Force (Join-Path $repoRoot "build")
    }

    $buildEnv = @{
        TMP = $buildTemp
        TEMP = $buildTemp
    }

    $usedTempShim = $false
    $originalPythonPath = $env:PYTHONPATH
    $script:CurrentPhase = "building wheel: probing python temp"
    if (-not (Test-PythonTempWrite -PythonExecutable $PythonCmd -ProbeTempDir $buildTemp)) {
        $script:CurrentPhase = "building wheel: installing temp shim"
        $shimDir = Join-Path $workspaceRoot "pep517-temp-shim"
        $safeTempDir = Join-Path $workspaceRoot "pep517-safe-temp"
        Write-PythonTempShim -ShimDir $shimDir -SafeTempDir $safeTempDir
        $buildEnv["TMP"] = $safeTempDir
        $buildEnv["TEMP"] = $safeTempDir
        if ($originalPythonPath) {
            $buildEnv["PYTHONPATH"] = "$shimDir;$originalPythonPath"
        }
        else {
            $buildEnv["PYTHONPATH"] = $shimDir
        }
        $usedTempShim = $true
    }

    $script:CurrentPhase = "building wheel: invoking pep517 build"
    $result = Invoke-ExternalCommand -FilePath $PythonCmd -Arguments @(
        "-m", "build", "--no-isolation", "--wheel", "--outdir", $distDir
    ) -WorkingDirectory $repoRoot -Environment $buildEnv

    if ($result.ExitCode -ne 0) {
        $script:CurrentPhase = "building wheel: invoking setup.py fallback"
        $fallback = Invoke-ExternalCommand -FilePath $PythonCmd -Arguments @(
            "setup.py", "bdist_wheel", "--dist-dir", $distDir
        ) -WorkingDirectory $repoRoot -Environment @{
            TMP = $buildTemp
            TEMP = $buildTemp
        }
        if ($fallback.ExitCode -ne 0) {
            $script:CurrentPhase = "building wheel: invoking manual fallback"
            $manualWheel = Build-ManualWheel -PythonCmd $PythonCmd
            $script:EnvironmentSummary["build_command"] = "manual-wheel-fallback"
            $script:EnvironmentSummary["wheel_path"] = $manualWheel
            $script:EnvironmentSummary["build_fallback_reason"] = "pep517 and setup.py were unavailable on this host"
            return $manualWheel
        }
        $result = $fallback
    }

    $script:CurrentPhase = "building wheel: locating artifact"
    $wheel = Get-ChildItem -Path $distDir -Filter *.whl | Sort-Object LastWriteTimeUtc -Descending | Select-Object -First 1
    if (-not $wheel) {
        throw "No wheel artifact was produced in $distDir."
    }

    $script:EnvironmentSummary["build_command"] = $result.Command
    $script:EnvironmentSummary["wheel_path"] = $wheel.FullName
    if ($usedTempShim) {
        $script:EnvironmentSummary["build_temp_shim"] = "enabled"
    }
    else {
        $script:EnvironmentSummary["build_temp_shim"] = "not needed"
    }

    return $wheel.FullName
}

function Get-ZipMemberNames([string]$ZipPath) {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        return @($zip.Entries | Sort-Object FullName | Select-Object -ExpandProperty FullName)
    }
    finally {
        $zip.Dispose()
    }
}

function Get-ZipEntryText([string]$ZipPath, [string]$EntryName) {
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $entry = $zip.GetEntry($EntryName)
        if ($null -eq $entry) {
            return $null
        }
        $stream = $entry.Open()
        $reader = New-Object System.IO.StreamReader($stream, [System.Text.Encoding]::UTF8)
        try {
            return $reader.ReadToEnd()
        }
        finally {
            $reader.Dispose()
            $stream.Dispose()
        }
    }
    finally {
        $zip.Dispose()
    }
}

function Get-ZipJson([string]$ZipPath, [string]$EntryName) {
    $text = Get-ZipEntryText -ZipPath $ZipPath -EntryName $EntryName
    if ([string]::IsNullOrWhiteSpace($text)) {
        return $null
    }
    return $text | ConvertFrom-Json
}

function Get-ZipSteps([string]$ZipPath) {
    $text = Get-ZipEntryText -ZipPath $ZipPath -EntryName "steps.jsonl"
    if ([string]::IsNullOrWhiteSpace($text)) {
        return @()
    }

    $steps = @()
    foreach ($line in ($text -split "`r?`n")) {
        if (-not [string]::IsNullOrWhiteSpace($line)) {
            $steps += ($line | ConvertFrom-Json)
        }
    }
    return $steps
}

function Get-OutputExcerpt([string]$Text, [int]$MaxLines = 12) {
    if ([string]::IsNullOrWhiteSpace($Text)) {
        return ""
    }
    return (($Text -split "`r?`n") | Select-Object -First $MaxLines) -join "`n"
}

function Write-JsonFile([string]$Path, $Value) {
    $json = $Value | ConvertTo-Json -Depth 100
    $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($Path, $json, $utf8NoBom)
}

function Get-OptionalObjectProperty($Object, [string]$Name) {
    if ($null -eq $Object) {
        return $null
    }
    $property = $Object.PSObject.Properties[$Name]
    if ($null -ne $property) {
        return $property.Value
    }
    return $null
}

function Install-WheelIntoVenv([string]$WheelPath, [string]$VenvDir) {
    $sitePackages = Join-Path $VenvDir "Lib\site-packages"
    $scriptsDir = Join-Path $VenvDir "Scripts"
    Ensure-Directory $sitePackages
    Ensure-Directory $scriptsDir

    $zip = [System.IO.Compression.ZipFile]::OpenRead($WheelPath)
    try {
        foreach ($entry in $zip.Entries) {
            $destination = Join-Path $sitePackages $entry.FullName
            if ([string]::IsNullOrEmpty($entry.Name)) {
                Ensure-Directory $destination
                continue
            }

            $parent = Split-Path -Parent $destination
            if ($parent) {
                Ensure-Directory $parent
            }

            $inputStream = $entry.Open()
            try {
                $outputStream = [System.IO.File]::Open($destination, [System.IO.FileMode]::Create, [System.IO.FileAccess]::Write)
                try {
                    $inputStream.CopyTo($outputStream)
                }
                finally {
                    $outputStream.Dispose()
                }
            }
            finally {
                $inputStream.Dispose()
            }
        }
    }
    finally {
        $zip.Dispose()
    }

    $cmdWrapper = @'
@echo off
"%~dp0python.exe" -m epi_cli.main %*
'@
    $cmdPath = Join-Path $scriptsDir "epi.cmd"
    Set-Content -Path $cmdPath -Value $cmdWrapper -Encoding ASCII

    return [pscustomobject]@{
        SitePackages = $sitePackages
        CommandPath = $cmdPath
    }
}

function New-MinimalBundle([string]$Path) {
    $bundle = [ordered]@{
        metadata = [ordered]@{
            workflow_id = "77777777-7777-4777-8777-777777777777"
            created_at = "2026-04-07T10:00:00Z"
            goal = "Minimal AGT to EPI sanity import"
            notes = "Small clean-room user-flow bundle."
            tags = @("agt", "clean-room", "minimal")
        }
        audit_logs = @(
            [ordered]@{
                entry_id = "min-1"
                timestamp = "2026-04-07T10:00:00Z"
                event_type = "tool_call"
                agent_did = "did:agentmesh:minimal-agent"
                action = "search"
                data = [ordered]@{
                    tool_name = "search"
                    query = "claim policy"
                }
                outcome = "success"
                policy_decision = "allow"
                matched_rule = "TOOL-SEARCH-1"
                trace_id = "trace-minimal-1"
            }
            [ordered]@{
                entry_id = "min-2"
                timestamp = "2026-04-07T10:00:02Z"
                event_type = "tool_response"
                agent_did = "did:agentmesh:minimal-agent"
                action = "search"
                data = [ordered]@{
                    tool_name = "search"
                    result = [ordered]@{
                        status = "ok"
                    }
                }
                outcome = "success"
                policy_decision = "allow"
                matched_rule = "TOOL-SEARCH-1"
                trace_id = "trace-minimal-1"
            }
            [ordered]@{
                entry_id = "min-3"
                timestamp = "2026-04-07T10:00:05Z"
                event_type = "policy_violation"
                agent_did = "did:agentmesh:minimal-agent"
                action = "issue_denial_notice"
                data = [ordered]@{
                    message = "Unauthorized tool access"
                }
                outcome = "denied"
                policy_decision = "deny"
                matched_rule = "AUTH-TOOL-1"
                trace_id = "trace-minimal-1"
            }
        )
        compliance_report = [ordered]@{
            report_id = "minimal-report-1"
            generated_at = "2026-04-07T10:00:10Z"
            framework = "demo"
            total_controls = 1
            controls_met = 0
            controls_partial = 0
            controls_failed = 1
            compliance_score = 0.0
            violations = @(
                [ordered]@{
                    violation_id = "V1"
                    control_id = "AUTH-TOOL-1"
                    severity = "high"
                    description = "Unauthorized tool access"
                    evidence = [ordered]@{
                        trace_id = "trace-minimal-1"
                        entry_id = "min-3"
                        matched_rule = "AUTH-TOOL-1"
                    }
                }
            )
        }
        policy_document = [ordered]@{
            version = "1.0"
            name = "tool_policy"
            rules = @(
                [ordered]@{
                    name = "no unauthorized tools"
                    action = "deny"
                }
            )
        }
        runtime_context = [ordered]@{
            runtime = "python"
            version = "3.11"
        }
        slo_data = [ordered]@{
            latency_ms = 120
        }
    }

    Write-JsonFile -Path $Path -Value $bundle
}

function Prepare-Inputs {
    Ensure-Directory $inputsDir
    Copy-Item -Path (Join-Path $repoRoot "tests\fixtures\agt\*.json") -Destination $inputsDir -Force

    New-MinimalBundle -Path (Join-Path $inputsDir "minimal_sanity.json")

    $unknownPayload = Get-Content -Path (Join-Path $inputsDir "audit_only.json") -Raw | ConvertFrom-Json
    $unknownPayload.audit_logs[0].event_type = "custom_event"
    $unknownPayload.audit_logs[0].PSObject.Properties.Remove("policy_decision")
    $unknownPayload.audit_logs[0].PSObject.Properties.Remove("matched_rule")
    Write-JsonFile -Path (Join-Path $inputsDir "strict_unknown_event.json") -Value $unknownPayload

    $unclassifiedPayload = Get-Content -Path (Join-Path $inputsDir "audit_only.json") -Raw | ConvertFrom-Json
    $unclassifiedPayload.audit_logs[0] | Add-Member -NotePropertyName custom_extra -NotePropertyValue "surprise" -Force
    Write-JsonFile -Path (Join-Path $inputsDir "strict_unclassified_field.json") -Value $unclassifiedPayload
}

function Get-ExpectationMap($InputPath, [bool]$ExpectAnalysis) {
    $payload = Get-Content -Path $InputPath -Raw | ConvertFrom-Json
    return [ordered]@{
        "manifest.json" = $true
        "steps.jsonl" = $true
        "policy.json" = ($null -ne (Get-OptionalObjectProperty -Object $payload -Name "policy_document"))
        "policy_evaluation.json" = ($null -ne (Get-OptionalObjectProperty -Object $payload -Name "compliance_report"))
        "analysis.json" = $ExpectAnalysis
        "artifacts/agt/mapping_report.json" = $true
    }
}

function Get-ArtifactObservation([string]$EpiPath) {
    $members = Get-ZipMemberNames -ZipPath $EpiPath
    $mappingReport = Get-ZipJson -ZipPath $EpiPath -EntryName "artifacts/agt/mapping_report.json"
    $analysis = Get-ZipJson -ZipPath $EpiPath -EntryName "analysis.json"
    $policyEvaluation = Get-ZipJson -ZipPath $EpiPath -EntryName "policy_evaluation.json"
    $steps = Get-ZipSteps -ZipPath $EpiPath

    return [pscustomobject]@{
        Members = $members
        MappingReport = $mappingReport
        Analysis = $analysis
        PolicyEvaluation = $policyEvaluation
        Steps = $steps
        StepKinds = @($steps | ForEach-Object { $_.kind })
    }
}

function Add-Failure([string]$Message) {
    $script:Failures.Add($Message) | Out-Null
}

function Validate-SuccessScenario($Scenario, $Observation, $ImportOutput) {
    $expectations = Get-ExpectationMap -InputPath $Scenario.InputPath -ExpectAnalysis $Scenario.ExpectAnalysis
    foreach ($member in $expectations.Keys) {
        $present = $Observation.Members -contains $member
        if ($present -ne $expectations[$member]) {
            Add-Failure("$($Scenario.Name): expected member '$member' present=$($expectations[$member]) but found present=$present.")
        }
    }

    foreach ($step in $Observation.Steps) {
        if ($null -eq $step.content.source_ref) {
            Add-Failure("$($Scenario.Name): imported step '$($step.kind)' is missing content.source_ref.")
        }
    }

    switch ($Scenario.Name) {
        "minimal_sanity" {
            if ($null -eq $Observation.PolicyEvaluation) {
                Add-Failure("minimal_sanity: policy_evaluation.json was not created.")
            }
        }
        "audit_only" {
            if ($Observation.StepKinds -notcontains "tool.call" -or $Observation.StepKinds -notcontains "tool.response") {
                Add-Failure("audit_only: expected tool.call and tool.response steps.")
            }
        }
        "flight_only" {
            if ($Observation.StepKinds -notcontains "policy.check") {
                Add-Failure("flight_only: expected a policy.check step in flight-only import.")
            }
        }
        "combined_clean" {
            if ($Observation.MappingReport.step_transformation.dedupe_strategy -ne "prefer-audit") {
                Add-Failure("combined_clean: expected dedupe_strategy=prefer-audit.")
            }
            if ([int]$Observation.MappingReport.step_transformation.duplicates_removed -lt 1) {
                Add-Failure("combined_clean: expected duplicates_removed >= 1.")
            }
            if (
                $Observation.MappingReport.dedupe_conflicts.Count -lt 1 -or
                $Observation.MappingReport.dedupe_conflicts[0].resolution -ne "preferred_audit"
            ) {
                Add-Failure("combined_clean: expected preferred_audit dedupe conflict resolution.")
            }
        }
        "combined_conflict" {
            if ($Observation.MappingReport.dedupe_conflicts.Count -lt 1) {
                Add-Failure("combined_conflict: expected a recorded dedupe conflict.")
            }
        }
        "no_violations" {
            if ($null -ne $Observation.Analysis -and $Observation.Analysis.fault_detected) {
                Add-Failure("no_violations: analysis unexpectedly detected a fault.")
            }
        }
        "heavy_violations" {
            if ($null -eq $Observation.Analysis) {
                Add-Failure("heavy_violations: analysis.json missing.")
            }
            elseif ($Observation.Analysis.primary_fault.severity -ne "critical") {
                Add-Failure("heavy_violations: expected primary_fault.severity=critical.")
            }
        }
        "analysis_none" {
            if ($Observation.Members -contains "analysis.json") {
                Add-Failure("analysis_none: analysis.json should be absent.")
            }
            if ($Observation.MappingReport.analysis.mode -ne "none") {
                Add-Failure("analysis_none: mapping report should record analysis mode 'none'.")
            }
            if ($ImportOutput -notmatch "analysis\.json will be omitted") {
                Add-Failure("analysis_none: CLI warning about omitted analysis.json was not shown.")
            }
        }
    }
}

function Invoke-Scenario($Scenario, [string]$EpiExe, [hashtable]$Environment) {
    $outputPath = Join-Path $outputsDir ($Scenario.Name + ".epi")
    if (Test-Path $outputPath) {
        Remove-Item -Path $outputPath -Force -ErrorAction SilentlyContinue
    }

    $importArgs = @("import", "agt", $Scenario.InputPath, "--out", $outputPath) + $Scenario.ExtraArgs
    $importResult = Invoke-ExternalCommand -FilePath $EpiExe -Arguments $importArgs -WorkingDirectory $workspaceRoot -Environment $Environment

    $result = [ordered]@{
        Name = $Scenario.Name
        Input = $Scenario.InputPath
        ExpectedSuccess = $Scenario.ExpectSuccess
        ImportCommand = $importResult.Command
        ImportExitCode = $importResult.ExitCode
        ImportOutput = $importResult.Output
        OutputPath = $outputPath
        OutputExists = (Test-Path $outputPath)
        VerifyCommand = $null
        VerifyExitCode = $null
        VerifyOutput = ""
        Members = @()
        MemberPresence = [ordered]@{}
        StepKinds = @()
        MappingInputCount = $null
        MappingOutputCount = $null
        DedupeStrategy = $null
        DedupeOutcome = $null
        UnknownEvents = @()
        AnalysisSynthesized = $null
        AnalysisMode = $null
        AnalysisHeadline = $null
        ExpectedFailurePattern = $Scenario.ExpectedFailurePattern
    }

    if (-not $Scenario.ExpectSuccess) {
        if ($importResult.ExitCode -eq 0) {
            Add-Failure("$($Scenario.Name): import unexpectedly succeeded.")
        }
        elseif ($Scenario.ExpectedFailurePattern -and $importResult.Output -notmatch $Scenario.ExpectedFailurePattern) {
            Add-Failure("$($Scenario.Name): failure output did not match /$($Scenario.ExpectedFailurePattern)/.")
        }

        return [pscustomobject]$result
    }

    if ($importResult.ExitCode -ne 0) {
        Add-Failure("$($Scenario.Name): import failed unexpectedly. See report for output.")
        return [pscustomobject]$result
    }

    if (-not (Test-Path $outputPath)) {
        Add-Failure("$($Scenario.Name): import succeeded but no .epi file was created.")
        return [pscustomobject]$result
    }

    $verifyResult = Invoke-ExternalCommand -FilePath $EpiExe -Arguments @("verify", $outputPath) -WorkingDirectory $workspaceRoot -Environment $Environment
    $result.VerifyCommand = $verifyResult.Command
    $result.VerifyExitCode = $verifyResult.ExitCode
    $result.VerifyOutput = $verifyResult.Output

    if ($verifyResult.ExitCode -ne 0) {
        Add-Failure("$($Scenario.Name): epi verify failed unexpectedly.")
    }

    $observation = Get-ArtifactObservation -EpiPath $outputPath
    $result.Members = $observation.Members
    $result.StepKinds = $observation.StepKinds

    $expectations = Get-ExpectationMap -InputPath $Scenario.InputPath -ExpectAnalysis $Scenario.ExpectAnalysis
    foreach ($member in $expectations.Keys) {
        $result.MemberPresence[$member] = ($observation.Members -contains $member)
    }

    if ($null -ne $observation.MappingReport) {
        $result.MappingInputCount = $observation.MappingReport.step_transformation.combined_input_count
        $result.MappingOutputCount = $observation.MappingReport.step_transformation.output_count
        $result.DedupeStrategy = $observation.MappingReport.step_transformation.dedupe_strategy
        if ($observation.MappingReport.dedupe_conflicts.Count -gt 0) {
            $result.DedupeOutcome = $observation.MappingReport.dedupe_conflicts[0].resolution
        }
        $result.UnknownEvents = @($observation.MappingReport.event_mapping.unknown | ForEach-Object { $_.source_type })
        $result.AnalysisSynthesized = $observation.MappingReport.analysis.synthesized
        $result.AnalysisMode = $observation.MappingReport.analysis.mode
    }

    if ($null -ne $observation.Analysis) {
        $result.AnalysisHeadline = $observation.Analysis.summary.headline
    }

    Validate-SuccessScenario -Scenario $Scenario -Observation $observation -ImportOutput $importResult.Output

    return [pscustomobject]$result
}

function Test-HelpSurface([string]$EpiExe, [hashtable]$Environment) {
    $helpResult = Invoke-ExternalCommand -FilePath $EpiExe -Arguments @("--help") -WorkingDirectory $workspaceRoot -Environment $Environment
    $requiredTokens = @("import", "verify", "view", "review")
    $missingTokens = @()
    foreach ($token in $requiredTokens) {
        if ($helpResult.Output -notmatch [regex]::Escape($token)) {
            $missingTokens += $token
        }
    }

    if ($helpResult.ExitCode -ne 0) {
        Add-Failure("epi --help failed in the clean-room environment.")
    }
    if ($missingTokens.Count -gt 0) {
        Add-Failure("epi --help is missing expected commands: $($missingTokens -join ', ').")
    }

    $script:InstallChecks["help_command"] = $helpResult.Command
    $script:InstallChecks["help_exit_code"] = $helpResult.ExitCode
    $script:InstallChecks["help_excerpt"] = Get-OutputExcerpt -Text $helpResult.Output -MaxLines 18
    $script:InstallChecks["commands_found"] = @($requiredTokens | Where-Object { $missingTokens -notcontains $_ })
    $script:InstallChecks["commands_missing"] = $missingTokens
}

function Write-ValidationReport {
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add("# Clean-Room AGT -> EPI User Validation") | Out-Null
    $lines.Add("") | Out-Null
    $lines.Add("Generated on: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss K')") | Out-Null
    $lines.Add(("Repo root: {0}" -f $repoRoot)) | Out-Null
    $lines.Add(("Workspace: {0}" -f $workspaceRoot)) | Out-Null
    $lines.Add("") | Out-Null

    $lines.Add("## Environment") | Out-Null
    foreach ($key in $script:EnvironmentSummary.Keys) {
        $lines.Add(("- {0}: {1}" -f $key, $script:EnvironmentSummary[$key])) | Out-Null
    }
    $lines.Add("") | Out-Null

    $lines.Add("## Install Flow") | Out-Null
    foreach ($key in $script:InstallChecks.Keys) {
        $value = $script:InstallChecks[$key]
        if ($value -is [System.Array]) {
            $value = ($value -join ", ")
        }
        $lines.Add(("- {0}: {1}" -f $key, $value)) | Out-Null
    }
    $lines.Add("") | Out-Null

    $lines.Add("## Scenario Matrix") | Out-Null
    $lines.Add("| Scenario | Expected | Import | Verify | Mapping Report | Notes |") | Out-Null
    $lines.Add("| --- | --- | --- | --- | --- | --- |") | Out-Null
    foreach ($result in $script:ScenarioResults) {
        $importStatus = if ($result.ExpectedSuccess) {
            if ($result.ImportExitCode -eq 0) { "PASS" } else { "FAIL" }
        }
        else {
            if ($result.ImportExitCode -ne 0) { "Expected fail" } else { "Unexpected pass" }
        }
        $verifyStatus = if ($result.ExpectedSuccess) {
            if ($result.VerifyExitCode -eq 0) { "PASS" } else { "FAIL" }
        }
        else {
            "N/A"
        }
        $mappingStatus = if ($result.ExpectedSuccess) {
            if ($result.MemberPresence["artifacts/agt/mapping_report.json"]) { "Present" } else { "Missing" }
        }
        else {
            "N/A"
        }
        $note = ""
        if (-not $result.ExpectedSuccess -and $result.ExpectedFailurePattern) {
            $note = "Expected /$($result.ExpectedFailurePattern)/"
        }
        elseif ($result.ExpectedSuccess -and $result.DedupeStrategy) {
            $note = "dedupe=$($result.DedupeStrategy)"
        }
        $lines.Add("| $($result.Name) | $($result.ExpectedSuccess) | $importStatus | $verifyStatus | $mappingStatus | $note |") | Out-Null
    }
    $lines.Add("") | Out-Null

    foreach ($result in $script:ScenarioResults) {
        $lines.Add("## $($result.Name)") | Out-Null
        $lines.Add(("- Input: {0}" -f $result.Input)) | Out-Null
        $lines.Add(("- Import command: {0}" -f $result.ImportCommand)) | Out-Null
        $lines.Add(("- Import exit code: {0}" -f $result.ImportExitCode)) | Out-Null
        if ($result.OutputExists) {
            $lines.Add(("- Output artifact: {0}" -f $result.OutputPath)) | Out-Null
        }
        if ($result.VerifyCommand) {
            $lines.Add(("- Verify command: {0}" -f $result.VerifyCommand)) | Out-Null
            $lines.Add(("- Verify exit code: {0}" -f $result.VerifyExitCode)) | Out-Null
        }
        $lines.Add("") | Out-Null

        $lines.Add("Import output excerpt:") | Out-Null
        $lines.Add('```text') | Out-Null
        $lines.Add((Get-OutputExcerpt -Text $result.ImportOutput -MaxLines 16)) | Out-Null
        $lines.Add('```') | Out-Null
        $lines.Add("") | Out-Null

        if ($result.VerifyCommand) {
            $lines.Add("Verify output excerpt:") | Out-Null
            $lines.Add('```text') | Out-Null
            $lines.Add((Get-OutputExcerpt -Text $result.VerifyOutput -MaxLines 18)) | Out-Null
            $lines.Add('```') | Out-Null
            $lines.Add("") | Out-Null
        }

        if ($result.ExpectedSuccess) {
            $lines.Add("Member presence:") | Out-Null
            foreach ($member in $result.MemberPresence.Keys) {
                $lines.Add(("- {0}: {1}" -f $member, $result.MemberPresence[$member])) | Out-Null
            }
            $lines.Add("") | Out-Null

            $lines.Add("Trust observations:") | Out-Null
            $lines.Add("- step kinds: $(([string[]]$result.StepKinds) -join ', ')") | Out-Null
            $lines.Add("- mapping input/output count: $($result.MappingInputCount) -> $($result.MappingOutputCount)") | Out-Null
            $lines.Add("- dedupe strategy: $($result.DedupeStrategy)") | Out-Null
            $lines.Add("- dedupe outcome: $($result.DedupeOutcome)") | Out-Null
            $unknownEventText = if ($result.UnknownEvents.Count -gt 0) { ([string[]]$result.UnknownEvents) -join ', ' } else { "none" }
            $lines.Add("- unknown events: $unknownEventText") | Out-Null
            $lines.Add("- analysis mode: $($result.AnalysisMode)") | Out-Null
            $lines.Add("- analysis synthesized: $($result.AnalysisSynthesized)") | Out-Null
            if ($result.AnalysisHeadline) {
                $lines.Add("- analysis headline: $($result.AnalysisHeadline)") | Out-Null
            }
            $lines.Add("") | Out-Null
        }
    }

    $minimalOk = $false
    $minimal = $script:ScenarioResults | Where-Object { $_.Name -eq "minimal_sanity" } | Select-Object -First 1
    if ($minimal -and $minimal.ImportExitCode -eq 0 -and $minimal.VerifyExitCode -eq 0) {
        $minimalOk = $true
    }
    $successCases = @($script:ScenarioResults | Where-Object { $_.ExpectedSuccess })
    $successfulDefaultCases = @(
        $successCases | Where-Object {
            $_.ImportExitCode -eq 0 -and
            $_.VerifyExitCode -eq 0 -and
            $_.MemberPresence["artifacts/agt/mapping_report.json"]
        }
    )
    $trustCasesOk = $successfulDefaultCases.Count -eq $successCases.Count
    $strictCases = @($script:ScenarioResults | Where-Object { -not $_.ExpectedSuccess })
    $strictFailures = @($strictCases | Where-Object { $_.ImportExitCode -ne 0 })
    $strictCasesOk = $strictFailures.Count -eq $strictCases.Count
    $commandsVisible = (@($script:InstallChecks["commands_missing"]).Count -eq 0)

    $lines.Add("## Acceptance Criteria") | Out-Null
    $lines.Add(("- Fresh user can go from wheel install to a signed .epi in one import command: {0}" -f $minimalOk)) | Out-Null
    $lines.Add(("- epi verify reports integrity success on the happy path: {0}" -f $trustCasesOk)) | Out-Null
    $lines.Add("- Artifact contents expose trace, policy/evaluation, and trust audit: $trustCasesOk") | Out-Null
    $lines.Add("- Strict mode fails on intentionally bad inputs: $strictCasesOk") | Out-Null
    $lines.Add("- Default mode succeeds on messy but valid AGT-shaped inputs: $trustCasesOk") | Out-Null
    $lines.Add(("- CLI help makes the flow discoverable (import, verify, view, review): {0}" -f $commandsVisible)) | Out-Null
    $lines.Add("") | Out-Null

    $lines.Add("## Manual Checklist") | Out-Null
    $lines.Add(("- Checklist file copied to: {0}" -f $checklistDest)) | Out-Null
    $lines.Add(("- Suggested viewer command: {0} view {1}" -f (Join-Path $venvDir "Scripts\epi.cmd"), (Join-Path $outputsDir "minimal_sanity.epi"))) | Out-Null
    $lines.Add("") | Out-Null

    if ($script:Failures.Count -gt 0) {
        $lines.Add("## Failures") | Out-Null
        foreach ($failure in $script:Failures) {
            $lines.Add("- $failure") | Out-Null
        }
        $lines.Add("") | Out-Null
    }
    else {
        $lines.Add("## Result") | Out-Null
        $lines.Add("- All scripted clean-room checks passed.") | Out-Null
        $lines.Add("") | Out-Null
    }

    Set-Content -Path $reportPath -Value ($lines -join [Environment]::NewLine) -Encoding UTF8
}

try {
    $script:CurrentPhase = "preparing workspace"
    Ensure-Directory $workspaceRoot
    Ensure-Directory $distDir
    Ensure-Directory $inputsDir
    Ensure-Directory $outputsDir
    Ensure-Directory $reportsDir
    Ensure-Directory $runtimeTemp
    Ensure-Directory $userHome
    Ensure-Directory (Join-Path $userHome "AppData\Roaming")
    Ensure-Directory (Join-Path $userHome "AppData\Local")

    if (Test-Path $checklistSource) {
        Copy-Item -Path $checklistSource -Destination $checklistDest -Force
    }

    $script:CurrentPhase = "resolving python"
    $pythonCmd = Resolve-PythonCommand $Python
    $basePythonCmd = Resolve-BasePythonCommand $pythonCmd
    $script:EnvironmentSummary["python"] = $pythonCmd
    $script:EnvironmentSummary["base_python"] = $basePythonCmd

    $script:CurrentPhase = "building wheel"
    $wheelPath = Build-ValidationWheel -PythonCmd $pythonCmd

    $script:CurrentPhase = "creating clean-room venv"
    $venvCreate = Invoke-ExternalCommand -FilePath $basePythonCmd -Arguments @("-m", "venv", "--without-pip", $venvDir) -WorkingDirectory $repoRoot -Environment @{
        TMP = $runtimeTemp
        TEMP = $runtimeTemp
    }
    if ($venvCreate.ExitCode -ne 0) {
        throw "Clean-room venv creation failed.`n$($venvCreate.Output)"
    }

    $cleanPython = Join-Path $venvDir "Scripts\python.exe"
    $hostSitePackages = Join-Path $repoRoot ".venv\Lib\site-packages"
    $runtimeShimDir = Join-Path $workspaceRoot "runtime-temp-shim"
    Write-PythonTempShim -ShimDir $runtimeShimDir -SafeTempDir $runtimeTemp
    $script:EnvironmentSummary["host_dependency_site_packages"] = $hostSitePackages
    $script:EnvironmentSummary["runtime_temp_shim"] = $runtimeShimDir
    $cleanEnv = @{
        HOME = $userHome
        USERPROFILE = $userHome
        APPDATA = (Join-Path $userHome "AppData\Roaming")
        LOCALAPPDATA = (Join-Path $userHome "AppData\Local")
        TMP = $runtimeTemp
        TEMP = $runtimeTemp
        PYTHONPATH = "$runtimeShimDir;$hostSitePackages"
    }

    $script:CurrentPhase = "installing wheel into clean-room venv"
    $installInfo = Install-WheelIntoVenv -WheelPath $wheelPath -VenvDir $venvDir
    $cleanEpi = $installInfo.CommandPath
    $script:InstallChecks["install_command"] = "manual wheel extraction into clean-room site-packages"
    $script:InstallChecks["install_exit_code"] = 0
    $script:InstallChecks["install_output_excerpt"] = ("Extracted {0} into {1}" -f $wheelPath, $installInfo.SitePackages)

    if (-not (Test-Path $cleanEpi)) {
        throw "Installed clean-room environment does not contain $cleanEpi."
    }

    $script:CurrentPhase = "checking CLI help"
    Test-HelpSurface -EpiExe $cleanEpi -Environment $cleanEnv
    $script:CurrentPhase = "preparing input bundles"
    Prepare-Inputs

    $scenarioSpecs = @(
        [pscustomobject]@{ Name = "minimal_sanity"; InputPath = (Join-Path $inputsDir "minimal_sanity.json"); ExtraArgs = @(); ExpectSuccess = $true; ExpectAnalysis = $true; ExpectedFailurePattern = $null },
        [pscustomobject]@{ Name = "audit_only"; InputPath = (Join-Path $inputsDir "audit_only.json"); ExtraArgs = @(); ExpectSuccess = $true; ExpectAnalysis = $true; ExpectedFailurePattern = $null },
        [pscustomobject]@{ Name = "flight_only"; InputPath = (Join-Path $inputsDir "flight_only.json"); ExtraArgs = @(); ExpectSuccess = $true; ExpectAnalysis = $true; ExpectedFailurePattern = $null },
        [pscustomobject]@{ Name = "combined_clean"; InputPath = (Join-Path $inputsDir "combined_clean.json"); ExtraArgs = @(); ExpectSuccess = $true; ExpectAnalysis = $true; ExpectedFailurePattern = $null },
        [pscustomobject]@{ Name = "combined_conflict"; InputPath = (Join-Path $inputsDir "combined_conflict.json"); ExtraArgs = @(); ExpectSuccess = $true; ExpectAnalysis = $true; ExpectedFailurePattern = $null },
        [pscustomobject]@{ Name = "combined_conflict_strict"; InputPath = (Join-Path $inputsDir "combined_conflict.json"); ExtraArgs = @("--strict", "--dedupe", "fail"); ExpectSuccess = $false; ExpectAnalysis = $false; ExpectedFailurePattern = "dedupe conflict" },
        [pscustomobject]@{ Name = "no_violations"; InputPath = (Join-Path $inputsDir "no_violations.json"); ExtraArgs = @(); ExpectSuccess = $true; ExpectAnalysis = $true; ExpectedFailurePattern = $null },
        [pscustomobject]@{ Name = "heavy_violations"; InputPath = (Join-Path $inputsDir "heavy_violations.json"); ExtraArgs = @(); ExpectSuccess = $true; ExpectAnalysis = $true; ExpectedFailurePattern = $null },
        [pscustomobject]@{ Name = "strict_unknown_event"; InputPath = (Join-Path $inputsDir "strict_unknown_event.json"); ExtraArgs = @("--strict", "--dedupe", "fail"); ExpectSuccess = $false; ExpectAnalysis = $false; ExpectedFailurePattern = "unknown AGT event type" },
        [pscustomobject]@{ Name = "strict_unclassified_field"; InputPath = (Join-Path $inputsDir "strict_unclassified_field.json"); ExtraArgs = @("--strict", "--dedupe", "fail"); ExpectSuccess = $false; ExpectAnalysis = $false; ExpectedFailurePattern = "unclassified field" },
        [pscustomobject]@{ Name = "analysis_none"; InputPath = (Join-Path $inputsDir "combined_clean.json"); ExtraArgs = @("--analysis", "none"); ExpectSuccess = $true; ExpectAnalysis = $false; ExpectedFailurePattern = $null }
    )

    $script:CurrentPhase = "running scenario matrix"
    foreach ($scenario in $scenarioSpecs) {
        $result = Invoke-Scenario -Scenario $scenario -EpiExe $cleanEpi -Environment $cleanEnv
        $script:ScenarioResults.Add($result) | Out-Null
    }
}
catch {
    Add-Failure(("{0}: {1}" -f $script:CurrentPhase, $_.Exception.Message))
}
finally {
    if ((Test-Path $checklistSource) -and -not (Test-Path $checklistDest)) {
        Ensure-Directory $reportsDir
        Copy-Item -Path $checklistSource -Destination $checklistDest -Force
    }
    Write-ValidationReport
}

Write-Host ""
Write-Host "Validation report: $reportPath"
Write-Host "Manual checklist: $checklistDest"

if ($script:Failures.Count -gt 0) {
    throw "Clean-room validation found $($script:Failures.Count) issue(s). See $reportPath."
}

if (-not $KeepWorkspace) {
    Write-Host "Workspace retained for inspection: $workspaceRoot"
}
