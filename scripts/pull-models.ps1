# Download models for a capability tier. Sizes are approximate download sizes (Q4 quantization).
# Tiers are about model SIZE; when newer models of the same size appear on
# https://ollama.com/library, swap the tags below.
param(
    [ValidateSet('small', 'medium', 'large', 'all')]
    [string]$Tier = 'medium'
)
$ErrorActionPreference = 'Stop'

$tiers = [ordered]@{
    # ~3-4 GB VRAM, very fast, basic quality
    small  = @('qwen3:4b', 'gemma3:4b')                 # 2.5 GB, 3.3 GB
    # ~6-11 GB VRAM, the "decent chatbot" sweet spot for a 16 GB GPU
    medium = @('qwen3:8b', 'gemma3:12b', 'qwen3:14b')   # 5.2 GB, 8.1 GB, 9.3 GB
    # ~13-16 GB VRAM, the largest that fits fully on an RX 9070 XT
    large  = @('gpt-oss:20b', 'mistral-small3.2:24b')   # 14 GB, 15 GB
}

$selected = if ($Tier -eq 'all') { $tiers.Values | ForEach-Object { $_ } } else { $tiers[$Tier] }

foreach ($model in $selected) {
    Write-Host "`n==> Pulling $model" -ForegroundColor Cyan
    ollama pull $model
    if ($LASTEXITCODE -ne 0) { throw "Failed to pull $model" }
}
Write-Host "`nInstalled models:" -ForegroundColor Green
ollama list
