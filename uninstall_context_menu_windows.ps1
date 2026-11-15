$Targets = @(
    "HKCU:\Software\Classes\Directory\shell\TagAudiobook",
    "HKCU:\Software\Classes\SystemFileAssociations\.m4b\shell\TagAudiobook",
    "HKCU:\Software\Classes\SystemFileAssociations\.mp3\shell\TagAudiobook"
)

foreach ($KeyPath in $Targets) {
    if (Test-Path $KeyPath) {
        Remove-Item -Path $KeyPath -Recurse -Force
        Write-Host "[-] Removed: $KeyPath" -ForegroundColor Yellow
    }
}

Write-Host "[+] 'Tag this' context menu removed cleanly." -ForegroundColor Green