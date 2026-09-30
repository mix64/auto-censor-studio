$ErrorActionPreference = 'Stop'
$taskPython = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $taskPython)) {
    & (Join-Path $PSScriptRoot 'setup.ps1')
}
Start-Process -FilePath $taskPython -ArgumentList '-m auto_censor_studio' -WorkingDirectory $PSScriptRoot -WindowStyle Hidden
