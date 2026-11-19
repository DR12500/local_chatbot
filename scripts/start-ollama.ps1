# Starts the Ollama server bound to localhost if it isn't already running.
$ErrorActionPreference = 'Stop'
$api = 'http://127.0.0.1:11434/api/version'

function Test-Ollama {
    try { Invoke-RestMethod $api -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}

if (Test-Ollama) { Write-Host 'Ollama already running.'; return }

$env:OLLAMA_HOST = '127.0.0.1:11434'
Write-Host '==> Starting Ollama server' -ForegroundColor Cyan
Start-Process ollama -ArgumentList 'serve' -WindowStyle Hidden

for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 500
    if (Test-Ollama) { Write-Host 'Ollama is up.'; return }
}
throw 'Ollama did not start within 15 s. Try running "ollama serve" manually to see the error.'
