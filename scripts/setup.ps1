# One-time setup: installs Ollama, locks it to localhost, downloads models for a tier.
#   powershell -ExecutionPolicy Bypass -File scripts\setup.ps1 -Tier medium
param(
    [ValidateSet('small', 'medium', 'large', 'all')]
    [string]$Tier = 'medium',
    # Where model weights are stored (they are large). Workspace convention: G:\ai-models\<tool>.
    [string]$ModelsDir = 'G:\ai-models\ollama-models'
)
$ErrorActionPreference = 'Stop'

function Find-Ollama {
    $cmd = Get-Command ollama -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $default = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
    if (Test-Path $default) { return $default }
    return $null
}

# 1. Settings first, so the Ollama app picks them up as soon as it starts:
#    API only on this machine, models in $ModelsDir.
New-Item -ItemType Directory -Force $ModelsDir | Out-Null
[Environment]::SetEnvironmentVariable('OLLAMA_HOST', '127.0.0.1:11434', 'User')
[Environment]::SetEnvironmentVariable('OLLAMA_MODELS', $ModelsDir, 'User')
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MODELS = $ModelsDir
Write-Host "Models will be stored in $ModelsDir"

# 2. Install Ollama (local LLM runtime, MIT licensed)
if (-not (Find-Ollama)) {
    Write-Host '==> Installing Ollama via winget' -ForegroundColor Cyan
    winget install --id Ollama.Ollama -e --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
    # Clean up the downloaded installer (~1 GB); it is not needed after installation.
    Get-ChildItem "$env:TEMP\WinGet" -Directory -Filter 'Ollama.Ollama*' -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -Confirm:$false -ErrorAction SilentlyContinue
}
$ollama = Find-Ollama
if (-not $ollama) { throw 'Ollama not found after install. Install it from https://ollama.com/download and re-run.' }
$ollamaDir = Split-Path $ollama
if (($env:Path -split ';') -notcontains $ollamaDir) { $env:Path += ";$ollamaDir" }
Write-Host "Ollama: $ollama"

# 3. Restart Ollama so it runs with the settings above (the installer may have
#    auto-started the tray app with the old environment).
Get-Process 'ollama app', 'ollama' -ErrorAction SilentlyContinue | Stop-Process -Force -Confirm:$false
Start-Sleep -Seconds 1
& "$PSScriptRoot\start-ollama.ps1"

# 4. Download models
& "$PSScriptRoot\pull-models.ps1" -Tier $Tier

Write-Host "`nSetup done. Run scripts\start.ps1 to open the chatbot." -ForegroundColor Green
Write-Host 'Privacy tip: in the Ollama tray app settings, keep "Expose Ollama to the network" OFF and turn' -ForegroundColor Yellow
Write-Host 'on "Airplane mode" if your version has it (disables Ollama cloud models and sign-in).' -ForegroundColor Yellow
