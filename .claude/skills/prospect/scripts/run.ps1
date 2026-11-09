# Launcher for the /prospect tool (Windows PowerShell, for setups without Git Bash).
# Finds a working Python 3.9+, installs it with winget if missing, then runs prospect.py.
$ErrorActionPreference = 'Stop'
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$check = 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)'

function Find-Python {
    foreach ($cand in @(@('python'), @('py', '-3'), @('python3'))) {
        $exe = $cand[0]
        if (Get-Command $exe -ErrorAction SilentlyContinue) {
            $pyArgs = @($cand | Select-Object -Skip 1)
            & $exe @pyArgs -c $check 2>$null | Out-Null
            if ($LASTEXITCODE -eq 0) {
                return (& $exe @pyArgs -c 'import sys; print(sys.executable)').Trim()
            }
        }
    }
    $paths = @(Get-ChildItem "$env:LOCALAPPDATA\Programs\Python\Python3*\python.exe" -ErrorAction SilentlyContinue) +
             @(Get-ChildItem "C:\Python3*\python.exe" -ErrorAction SilentlyContinue) +
             @(Get-ChildItem "$env:ProgramFiles\Python3*\python.exe" -ErrorAction SilentlyContinue)
    foreach ($p in $paths) {
        & $p.FullName -c $check 2>$null | Out-Null
        if ($LASTEXITCODE -eq 0) { return $p.FullName }
    }
    return $null
}

$py = Find-Python
if (-not $py) {
    Write-Host 'Python 3 was not found - installing it (one-time setup)...'
    if (Get-Command winget -ErrorAction SilentlyContinue) {
        winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    } else {
        Write-Host 'winget is not available. Install Python from https://www.python.org/downloads/ (tick Add to PATH).'
    }
    $py = Find-Python
}
if (-not $py) {
    Write-Host 'ERROR: Python 3.9+ is required and could not be installed automatically.'
    exit 3
}
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONDONTWRITEBYTECODE = '1'
& $py (Join-Path $scriptDir 'prospect.py') @args
exit $LASTEXITCODE
