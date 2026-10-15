param(
    [string]$OutputRoot = "",
    [string]$PackageName = "researcher_radar_deploy_$(Get-Date -Format yyyyMMdd)"
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputRoot) {
    $OutputRoot = Split-Path -Parent $ProjectRoot
}
$PackageDir = Join-Path $OutputRoot $PackageName
$ZipPath = "$PackageDir.zip"

if (Test-Path -LiteralPath $PackageDir) {
    throw "Package directory already exists: $PackageDir"
}
if (Test-Path -LiteralPath $ZipPath) {
    throw "Zip already exists: $ZipPath"
}

New-Item -ItemType Directory -Path $PackageDir | Out-Null

$excludeDirs = @(
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "data",
    "logs",
    "deploy",
    "staticfiles",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    ".vite",
    "logs",
    # Local Codex/desktop runtime state (never part of a server release).
    ".sandbox",
    ".sandbox-bin",
    ".sandbox-secrets",
    ".tmp",
    "ambient-suggestions",
    "cache",
    "computer-use",
    "plugins",
    "rules",
    "sessions",
    "skills",
    "sqlite",
    "thread-writer-locks",
    "tmp",
    "vendor_imports",
    "visualizations",
    "tests",
    "literature_daily_deploy_*",
    "researcher_radar_deploy_*"
)

$excludeFiles = @(
    "db.sqlite3",
    "*.pyc",
    "*.pyo",
    "*.log",
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    ".DS_Store",
    "Thumbs.db",
    # Local Codex/desktop runtime files and databases.
    ".cockpit_codex_auth.json*",
    ".codex-global-state.json*",
    ".sandbox_migration",
    "AGENTS.md",
    "auth.json*",
    "cap_sid",
    "config.toml",
    "installation_id",
    "models_cache.json",
    "session_index.jsonl",
    "*.sqlite",
    "*.sqlite-shm",
    "*.sqlite-wal",
    "literature_daily_deploy_*.zip",
    "researcher_radar_deploy_*.zip",
    "handoff.md",
    "FRONTEND_DESIGN.md"
)

$xd = @("/XD") + $excludeDirs
$xf = @("/XF") + $excludeFiles

robocopy $ProjectRoot $PackageDir /E @xd @xf /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -gt 7) {
    throw "robocopy failed with exit code $LASTEXITCODE"
}

$FrontendDist = Join-Path $ProjectRoot "frontend\dist"
if (-not (Test-Path -LiteralPath (Join-Path $FrontendDist "index.html"))) {
    throw "Frontend build is missing. Run the frontend build before packaging: $FrontendDist"
}
Copy-Item -LiteralPath $FrontendDist -Destination (Join-Path $PackageDir "frontend\dist") -Recurse -Force

Copy-Item -LiteralPath (Join-Path $ProjectRoot "scripts\deploy_package.sh") -Destination (Join-Path $PackageDir "deploy.sh") -Force

Compress-Archive -Path (Join-Path $PackageDir "*") -DestinationPath $ZipPath -CompressionLevel Optimal

Write-Host "Package directory: $PackageDir"
Write-Host "Zip package: $ZipPath"
