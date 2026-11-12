# Copies Color Under Pressure: RNG from the ManStudio folder into this project
# (code + any music / sound files; never saves, logs or account files).
# Run it after changing the game, then push: GitHub builds a new APK.
# RNG makes its music and sounds in code (numpy), so today there are no sound files - but if a
# future version adds mp3/ogg/wav files or a music_cache folder, they are copied in too.
$ErrorActionPreference = 'Stop'
$src = Join-Path $env:USERPROFILE 'Desktop\ManStudio\ColorRNG_MSIX'
$dst = Join-Path $PSScriptRoot 'app'
Copy-Item (Join-Path $src 'color_rng.py') $dst -Force
$snd = Get-ChildItem $src -File | Where-Object { $_.Extension -in '.mp3', '.ogg', '.wav' }
$snd | ForEach-Object { Copy-Item $_.FullName $dst -Force }
if (Test-Path (Join-Path $src 'music_cache')) {
    Copy-Item (Join-Path $src 'music_cache') $dst -Recurse -Force
}
Copy-Item (Join-Path $src 'msix_layout\Assets\Square150x150Logo.png') (Join-Path $PSScriptRoot 'icon.png') -Force
Copy-Item (Join-Path $src 'msix_layout\Assets\SplashScreen.png') (Join-Path $PSScriptRoot 'presplash.png') -Force
Write-Output "synced: color_rng.py + $(@($snd).Count) sound files"
