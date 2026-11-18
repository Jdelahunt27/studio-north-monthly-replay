# Speak each line of demo/narration.json with Windows' built-in text-to-speech (System.Speech).
# Writes demo/narration/<id>.wav and demo/narration/durations.json (milliseconds per line).
param([string]$Voice = "Microsoft Zira Desktop", [int]$Rate = 0)
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$out = Join-Path $here "demo\narration"
New-Item -ItemType Directory -Force $out | Out-Null
Add-Type -AssemblyName System.Speech
$lines = Get-Content (Join-Path $here "demo\narration.json") -Raw | ConvertFrom-Json
$durations = [ordered]@{}
foreach ($line in $lines) {
    $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
    $synth.SelectVoice($Voice)
    $synth.Rate = $Rate
    $wav = Join-Path $out "$($line.id).wav"
    $fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono)
    $synth.SetOutputToWaveFile($wav, $fmt)
    $synth.Speak($line.say)
    $synth.Dispose()
    $bytes = (Get-Item $wav).Length - 44
    $durations[$line.id] = [int]($bytes / (48000 * 2) * 1000)
}
$durations | ConvertTo-Json | Out-File -Encoding ascii (Join-Path $out "durations.json")
$total = ($durations.Values | Measure-Object -Sum).Sum / 1000
"spoke $($lines.Count) lines, $total s of narration"
