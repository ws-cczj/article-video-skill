param(
    [string]$Storyboard,
    [string]$Voice,
    [switch]$ListVoices,
    [ValidateRange(-10,10)][int]$Rate = 0
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$speaker = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
    $voices = @($speaker.GetInstalledVoices() | Where-Object Enabled)
    if ($ListVoices) {
        $voices | ForEach-Object { $_.VoiceInfo } | Select-Object Name,Culture,Gender
        return
    }
    if (-not $Storyboard) { throw 'Provide -Storyboard or -ListVoices.' }
    $storyPath = (Resolve-Path -LiteralPath $Storyboard).Path
    $projectDir = Split-Path -Parent $storyPath
    $story = Get-Content -LiteralPath $storyPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $story.scenes -or -not $story.language) { throw 'Scenes and language required.' }
    $chosen = @($voices | Where-Object { $_.VoiceInfo.Culture.Name -eq $story.language -and (-not $Voice -or $_.VoiceInfo.Name -eq $Voice) })
    if ($chosen.Count -eq 0) { throw 'No matching language voice. Use -ListVoices.' }
    $speaker.SelectVoice($chosen[0].VoiceInfo.Name)
    $speaker.Rate = $Rate
    $seen = @{}
    foreach ($scene in $story.scenes) {
        if ($scene.id -notmatch '^[A-Za-z0-9_-]+$' -or $seen.ContainsKey($scene.id)) { throw 'Invalid or duplicate scene ID.' }
        $seen[$scene.id] = $true
        if (-not $scene.narration) { throw "Missing narration: $($scene.id)" }
    }
    foreach ($scene in $story.scenes) {
        # Synthesize each authored sentence separately: cue boundaries use actual WAV lengths.
        $chunks = @([regex]::Matches($scene.narration, '[^。！？!?\r\n]+[。！？!?]?') | ForEach-Object { $_.Value.Trim() } | Where-Object { $_ })
        $segments = @()
        $idx = 0
        foreach ($chunk in $chunks) {
            $idx++
            $relative = 'audio/{0}/{1:d3}.wav' -f $scene.id, $idx
            $wavPath = Join-Path $projectDir $relative
            [System.IO.Directory]::CreateDirectory((Split-Path -Parent $wavPath)) | Out-Null
            $speaker.SetOutputToWaveFile($wavPath)
            $speaker.Speak([string]$chunk)
            $speaker.SetOutputToNull()
            $segments += @{ text = $chunk; audio = $relative }
        }
        $manifest = @{ voice = $chosen[0].VoiceInfo.Name; narration = $scene.narration; segments = @($segments) }
        $relativeManifest = "audio/$($scene.id)/timing.json"
        $manifest | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath (Join-Path $projectDir $relativeManifest) -Encoding UTF8
        $scene | Add-Member -NotePropertyName timing -NotePropertyValue $relativeManifest -Force
        $scene.PSObject.Properties.Remove('speech')
        Write-Output "Synthesized $($scene.id): $($chunks.Count) sentences"
    }
    $story | ConvertTo-Json -Depth 30 | Set-Content -LiteralPath $storyPath -Encoding UTF8
} finally {
    $speaker.Dispose()
}
