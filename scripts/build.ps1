param([switch]$NoUPX)
$ErrorActionPreference = 'Stop'
Set-Location (Split-Path -Parent $PSScriptRoot)
$pythonPath = Join-Path (Get-Location) '.venv/Scripts/python.exe'
& $pythonPath -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
$buildArgs = @('-m', 'PyInstaller', '--clean', '--noconfirm')
if (-not $NoUPX) {
    $upxPath = Join-Path (Get-Location) 'tools/upx'
    if (-not (Test-Path (Join-Path $upxPath 'upx.exe'))) { throw 'Place official UPX upx.exe in tools/upx, or use -NoUPX' }
    $buildArgs += @('--upx-dir', $upxPath)
}
$buildArgs += 'build.spec'
& $pythonPath @buildArgs
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
foreach ($testMode in @('--smoke-test', '--native-smoke-test')) {
    $testProcess = Start-Process -FilePath (Join-Path (Get-Location) 'dist/QQPersonaAgent.exe') -ArgumentList $testMode -PassThru -WindowStyle Hidden
    if (-not $testProcess.WaitForExit(60000)) { $testProcess.Kill(); throw 'Packaged GUI smoke timed out' }
    if ($testProcess.ExitCode -ne 0) { throw 'Packaged GUI smoke failed' }
}
Get-FileHash 'dist/QQPersonaAgent.exe' -Algorithm SHA256
