# Starts Ollama (if needed) and the chat UI, then opens it in the browser.
param([int]$Port = 8765)
$ErrorActionPreference = 'Stop'

& "$PSScriptRoot\start-ollama.ps1"

$python = (Get-Command python -ErrorAction SilentlyContinue)
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) { throw 'Python 3.8+ is required for the UI server.' }

$server = Join-Path $PSScriptRoot '..\app\server.py'
Start-Process "http://127.0.0.1:$Port"
& $python.Source $server --port $Port
