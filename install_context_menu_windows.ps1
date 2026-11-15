$AppDir = $PSScriptRoot
$PythonExe = Join-Path $AppDir "venv\Scripts\python.exe"
$TaggerScript = Join-Path $AppDir "tagger.py"

if (-not (Test-Path $PythonExe)) {
    Write-Error "Could not find virtual environment Python at: $PythonExe"
    exit 1
}

if (-not (Test-Path $TaggerScript)) {
    Write-Error "Could not find tagger.py at: $TaggerScript"
    exit 1
}

$CommandValue = "cmd.exe /k `"`"$PythonExe`" `"$TaggerScript`" `"%1`"`""

$Targets = @(
    "HKCU:\Software\Classes\Directory\shell\TagAudiobook",
    "HKCU:\Software\Classes\SystemFileAssociations\.m4b\shell\TagAudiobook",
    "HKCU:\Software\Classes\SystemFileAssociations\.mp3\shell\TagAudiobook"
)

foreach ($KeyPath in $Targets) {
    New-Item -Path $KeyPath -Force | Out-Null
    Set-ItemProperty -Path $KeyPath -Name "(Default)" -Value "Tag this"
    Set-ItemProperty -Path $KeyPath -Name "Icon" -Value "imageres.dll,-108"

    $CmdPath = Join-Path $KeyPath "command"
    New-Item -Path $CmdPath -Force | Out-Null
    Set-ItemProperty -Path $CmdPath -Name "(Default)" -Value $CommandValue
}

Write-Host "[+] 'Tag this' context menu added successfully for folders, .m4b, and .mp3 files." -ForegroundColor Green