param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Targets
)

$repoRoot = Split-Path -Parent $PSScriptRoot
$tmpRoot = Join-Path $repoRoot ".tmp"
$baseTemp = Join-Path $tmpRoot "pytest-basetemp-stable"

New-Item -ItemType Directory -Force -Path $tmpRoot | Out-Null
New-Item -ItemType Directory -Force -Path $baseTemp | Out-Null

$env:TMP = $tmpRoot
$env:TEMP = $tmpRoot

python -m pytest --basetemp $baseTemp @Targets
