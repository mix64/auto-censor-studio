$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    if (Get-Command py -ErrorAction SilentlyContinue) {
        & py -3 -m venv (Join-Path $taskRoot '.venv')
    } elseif (Get-Command python -ErrorAction SilentlyContinue) {
        & python -m venv (Join-Path $taskRoot '.venv')
    } else {
        throw 'Install Python 3.12 or later, then run setup.ps1 again.'
    }
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the virtual environment.' }
}
& $taskPython -m pip install --disable-pip-version-check -e $taskRoot
if ($LASTEXITCODE -ne 0) { throw 'Could not install Auto Censor Studio.' }
& $taskPython -m auto_censor_studio.models
if ($LASTEXITCODE -ne 0) { throw 'Could not prepare the models.' }
Write-Host 'Ready. Open Start.cmd to launch Auto Censor Studio.'
