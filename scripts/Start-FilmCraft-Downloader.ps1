param(
  [string]$FilmCraftExe = 'C:\Program Files\FilmCraft\filmcraft.exe',
  [string]$FilmCraftCli = 'C:\Program Files\FilmCraft\filmcraft-cli.exe',
  [int]$ControlPort = 9876
)
$ErrorActionPreference = 'Stop'

if (-not (Test-Path $FilmCraftExe)) { throw "FilmCraft executable not found: $FilmCraftExe. Pass -FilmCraftExe with the installed path." }
if (-not (Test-Path $FilmCraftCli)) { throw "FilmCraft CLI not found: $FilmCraftCli. Pass -FilmCraftCli with the installed path." }

# The control token must be shared by the desktop process and its CLI bridge.
$bytes = New-Object byte[] 32
$rng = [System.Security.Cryptography.RandomNumberGenerator]::Create()
$rng.GetBytes($bytes)
$rng.Dispose()
$env:FILMCRAFT_CONTROL_TOKEN = ([Convert]::ToHexString($bytes)).ToLowerInvariant()
$env:FILMCRAFT_CONTROL_ADDRESS = "127.0.0.1:$ControlPort"
$env:FILMCRAFT_CLI_PATH = $FilmCraftCli

$listener = Get-NetTCPConnection -LocalPort $ControlPort -State Listen -ErrorAction SilentlyContinue
if ($listener) { throw "Port $ControlPort is already in use. Close the existing FilmCraft instance or choose another -ControlPort." }

Write-Host 'Starting FilmCraft with its authenticated local control channel…'
Start-Process -FilePath $FilmCraftExe -ArgumentList @('--control', [string]$ControlPort)
Start-Sleep -Seconds 2
Write-Host 'Starting YouTube Export Panel. Keep this PowerShell window open so the shared token remains available.'
Set-Location (Join-Path $PSScriptRoot '..')
npm start
