param(
    [switch]$WriteReportingOnly,
    [switch]$AllowResearchRegeneration
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

function Invoke-QreCommand {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Title,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments
    )

    Write-Host ""
    Write-Host "=== $Title ==="
    Write-Host ("python " + ($Arguments -join " "))
    & python @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: python $($Arguments -join ' ')"
    }
}

function Read-QreJson {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }
    return Get-Content -Raw -LiteralPath $Path | ConvertFrom-Json
}

if ($AllowResearchRegeneration) {
    Write-Warning "AllowResearchRegeneration was requested. The verifier will only pass the explicit flag to reporting.qre_controlled_artifact_regeneration_runner; it will not call research.run_research directly."
}

Invoke-QreCommand "Closed-loop materialization dry check" @(
    "-m", "reporting.qre_closed_loop_materialization_runner", "--no-write", "--indent", "2"
)
Invoke-QreCommand "Market observation hypothesis readiness" @(
    "-m", "reporting.qre_market_observation_hypothesis_readiness"
)
Invoke-QreCommand "Executable validation request" @(
    "-m", "reporting.qre_executable_validation_request"
)
Invoke-QreCommand "Validation request dry-run runner" @(
    "-m", "reporting.qre_validation_request_dry_run_runner"
)
Invoke-QreCommand "Executable hypothesis identity bridge diagnostics" @(
    "-m", "reporting.qre_executable_hypothesis_identity_bridge_diagnostics", "--no-write", "--indent", "2"
)

Invoke-QreCommand "Selection route materialization" @(
    "-m", "reporting.qre_selection_route_materialization"
)
Invoke-QreCommand "Selection route validation flow" @(
    "-m", "reporting.qre_selection_route_validation_flow"
)
Invoke-QreCommand "Selection closed-loop preflight" @(
    "-m", "reporting.qre_selection_closed_loop_preflight"
)

Invoke-QreCommand "Controlled artifact regeneration backup plan" @(
    "-m", "reporting.qre_controlled_artifact_regeneration_backup_plan"
)

$runnerArgs = @("-m", "reporting.qre_controlled_artifact_regeneration_runner")
if ($AllowResearchRegeneration) {
    $runnerArgs += "--allow-research-regeneration"
} elseif ($WriteReportingOnly) {
    $runnerArgs += "--write-reporting-only"
} else {
    $runnerArgs += "--dry-run"
}
Invoke-QreCommand "Controlled artifact regeneration runner" $runnerArgs

Invoke-QreCommand "Post-run evidence promotion audit" @(
    "-m", "reporting.qre_post_run_evidence_promotion_audit"
)
Invoke-QreCommand "Operator closed-loop report" @(
    "-m", "reporting.qre_operator_closed_loop_report"
)

$controlled = Read-QreJson "logs/qre_controlled_artifact_regeneration/latest.json"
$audit = Read-QreJson "logs/qre_post_run_evidence_promotion_audit/latest.json"
$operator = Read-QreJson "logs/qre_operator_closed_loop_report/latest.json"
$selectionFlow = Read-QreJson "logs/qre_selection_route_validation_flow/latest.json"
$selectionPreflight = Read-QreJson "logs/qre_selection_closed_loop_preflight/latest.json"

Write-Host ""
Write-Host "=== QRE Closed-Loop E2E Summary ==="
if ($operator -ne $null) {
    Write-Host "loop_status: $($operator.loop_status)"
    Write-Host "next_operator_action: $($operator.next_operator_action)"
}
if ($selectionFlow -ne $null) {
    Write-Host "selection_request_ready_for_operator_review: $($selectionFlow.counts.request_ready_for_operator_review)"
    Write-Host "selection_dry_run_ready: $($selectionFlow.counts.dry_run_ready)"
}
if ($selectionPreflight -ne $null) {
    Write-Host "selection_route_ready: $($selectionPreflight.selection_route.ready)"
    Write-Host "selection_controlled_regeneration_can_be_considered: $($selectionPreflight.controlled_regeneration_preflight.can_be_considered)"
}
if ($controlled -ne $null) {
    Write-Host "controlled_regeneration_mode: $($controlled.mode)"
    Write-Host "controlled_regeneration_recommendation: $($controlled.final_recommendation)"
    Write-Host "backups_created_count: $(@($controlled.backups_created).Count)"
    Write-Host "executed_research_regeneration: $($controlled.executed_research_regeneration)"
}
if ($audit -ne $null) {
    Write-Host "audit_status: $($audit.final_recommendation)"
    Write-Host "audit_next_action: $($audit.next_action)"
}

Write-Host ""
Write-Host "Default verification does not call live, paper, shadow, broker, risk, execution, scheduler, Codex, or research.run_research paths."
