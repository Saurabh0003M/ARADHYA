# ARADHYA Lite one-time setup: venv + deps + pre-rendered "Yes sir?" ack.
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# Python 3.11 required: 3.10 fails (RealtimeSTT/scipy pins), 3.13 breaks openwakeword.
$use311 = $false
try { & py -3.11 -c "exit()"; if ($LASTEXITCODE -eq 0) { $use311 = $true } } catch {}
if (-not $use311) {
    throw "Python 3.11 not found. Install it first:  winget install Python.Python.3.11"
}
if (-not (Test-Path .venv)) {
    Write-Host "[1/3] creating venv (Python 3.11)..."
    py -3.11 -m venv .venv
} else {
    Write-Host "[1/3] venv exists, reusing"
}

Write-Host "[2/3] installing requirements (first run downloads ~1 GB incl. CPU torch; be patient)..."
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\pip.exe install -r requirements.txt
if ($LASTEXITCODE -ne 0) { throw "pip install failed (exit $LASTEXITCODE) - see output above" }

Write-Host "[3/3] pre-rendering acknowledgment WAV..."
New-Item -ItemType Directory -Force assets | Out-Null
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SetOutputToWaveFile("$PSScriptRoot\assets\ack.wav")
$synth.Speak("Yes sir?")
$synth.Dispose()

Write-Host ""
Write-Host "Setup complete. Optional but recommended for the Indian-English neural voice:"
Write-Host "    winget install mpv    (EdgeEngine needs mpv; otherwise the offline Windows voice is used)"
Write-Host "Start with:  .venv\Scripts\python aradhya_lite.py"
