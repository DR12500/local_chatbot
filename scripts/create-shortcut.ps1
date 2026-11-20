# Creates a "Local Chatbot" shortcut (Desktop and Start menu) that opens the model launcher
# without a console window.
$ErrorActionPreference = 'Stop'

$python = (Get-Command python -ErrorAction Stop).Source
$pythonw = Join-Path (Split-Path $python) 'pythonw.exe'
if (-not (Test-Path $pythonw)) { throw "pythonw.exe not found next to $python" }
$launcher = (Resolve-Path (Join-Path $PSScriptRoot '..\app\launcher.py')).Path

$shell = New-Object -ComObject WScript.Shell
$targets = @(
    [Environment]::GetFolderPath('Desktop'),
    (Join-Path ([Environment]::GetFolderPath('StartMenu')) 'Programs')
)
foreach ($dir in $targets) {
    $lnk = $shell.CreateShortcut((Join-Path $dir 'Local Chatbot.lnk'))
    $lnk.TargetPath = $pythonw
    $lnk.Arguments = "`"$launcher`""
    $lnk.WorkingDirectory = Split-Path $launcher
    $lnk.Description = 'Choose a local model and open the private chatbot'
    $ollamaIcon = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama app.exe'
    if (Test-Path $ollamaIcon) { $lnk.IconLocation = "$ollamaIcon,0" }
    $lnk.Save()
    Write-Host "Created $($lnk.FullName)"
}
