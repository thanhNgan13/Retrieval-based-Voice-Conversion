# Auto-select GPU or CPU: uses NVIDIA if nvidia-smi is available on this machine.
# Env: $env:RVC_DOCKER_MODE = "auto" | "cpu" | "gpu"  (default: auto)
#      $env:RVC_FORCE_CPU = "1"  or  $env:RVC_FORCE_GPU = "1"
[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$ComposeArgs
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location (Split-Path -Parent $scriptDir)

$mode = if ($env:RVC_DOCKER_MODE) { $env:RVC_DOCKER_MODE } else { "auto" }
if ($env:RVC_FORCE_CPU -eq "1") { $mode = "cpu" }
if ($env:RVC_FORCE_GPU -eq "1") { $mode = "gpu" }

$hasNvidiaSmi = $false
try {
  $null = Get-Command nvidia-smi -ErrorAction Stop
  $null = & nvidia-smi -L 2>&1
  if ($LASTEXITCODE -eq 0) { $hasNvidiaSmi = $true }
} catch { }

$extra = if ($null -ne $ComposeArgs -and $ComposeArgs.Count -gt 0) { $ComposeArgs } else { @() }

function Invoke-ComposeWithGpu {
  if ($extra.Count -gt 0) {
    & docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build @extra
  } else {
    & docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build
  }
}
function Invoke-ComposeCpu {
  if ($extra.Count -gt 0) {
    & docker compose -f docker-compose.yml up --build @extra
  } else {
    & docker compose -f docker-compose.yml up --build
  }
}

switch ($mode) {
  "cpu" {
    Write-Host "[RVC] Docker: forced CPU (no GPU pass-through from compose)"
    Invoke-ComposeCpu
  }
  "gpu" {
    Write-Host "[RVC] Docker: forced GPU (docker-compose.gpu.yml)"
    Invoke-ComposeWithGpu
  }
  default {
    if ($hasNvidiaSmi) {
      Write-Host "[RVC] Docker: host NVIDIA driver detected (nvidia-smi) - using GPU compose file"
      Write-Host "[RVC] If the container still shows CUDA: False, install/configure NVIDIA Container Toolkit for Docker (WSL2)."
      Invoke-ComposeWithGpu
    } else {
      Write-Host "[RVC] Docker: nvidia-smi not available - using CPU (no --gpus)"
      Write-Host "[RVC] To override: `$env:RVC_DOCKER_MODE='gpu' then run this script"
      Invoke-ComposeCpu
    }
  }
}
