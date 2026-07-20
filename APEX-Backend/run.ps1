# Starts the backend cleanly on the given port.
#
# Before launching it frees the port: it kills any uvicorn server for this app
# AND any orphaned reload workers (the multiprocessing children uvicorn spawns
# on Windows) that may still be holding the socket. This prevents a stale
# process from silently serving old code on a port your new server can't bind.
#
# Usage:
#   ./run.ps1                # port 8000, with reload (watches app/ only)
#   ./run.ps1 -Port 8001
#   ./run.ps1 -NoReload      # single process, no file watching

param(
    [int]$Port = 8000,
    [switch]$NoReload
)

$ErrorActionPreference = "SilentlyContinue"

function Stop-StaleServers([int]$targetPort) {
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        $pidsToKill = @()

        # 1. Anything currently holding the port (any TCP state).
        $conns = Get-NetTCPConnection -LocalPort $targetPort -ErrorAction SilentlyContinue
        if ($conns) { $pidsToKill += ($conns | Select-Object -ExpandProperty OwningProcess) }

        # 2. Uvicorn supervisors for THIS app.
        $pidsToKill += (Get-CimInstance Win32_Process -Filter "name='python.exe'" |
            Where-Object { $_.CommandLine -like '*uvicorn*app.main*' } |
            Select-Object -ExpandProperty ProcessId)

        # 3. Orphaned reload workers (multiprocessing spawn children) — only if
        #    the port is still occupied after steps 1-2 on a later pass.
        if ($attempt -gt 0) {
            $pidsToKill += (Get-CimInstance Win32_Process -Filter "name='python.exe'" |
                Where-Object { $_.CommandLine -like '*multiprocessing*spawn*' } |
                Select-Object -ExpandProperty ProcessId)
        }

        $pidsToKill = $pidsToKill | Where-Object { $_ -and $_ -ne 0 } | Select-Object -Unique
        if (-not $pidsToKill) { break }

        foreach ($procId in $pidsToKill) {
            try { Stop-Process -Id $procId -Force -ErrorAction Stop; Write-Host "  freed: killed PID $procId" } catch {}
        }
        Start-Sleep -Milliseconds 600

        if (-not (Get-NetTCPConnection -LocalPort $targetPort -State Listen -ErrorAction SilentlyContinue)) { break }
    }

    if (Get-NetTCPConnection -LocalPort $targetPort -State Listen -ErrorAction SilentlyContinue) {
        Write-Warning "Port $targetPort still appears occupied. Close the terminal running it, or reboot if it persists."
    }
}

Set-Location -Path $PSScriptRoot
Write-Host "Ensuring port $Port is free..."
Stop-StaleServers -targetPort $Port

Write-Host "Starting backend on port $Port ..."
if ($NoReload) {
    uvicorn app.main:app --port $Port
} else {
    # --reload-dir app: watch only source, NOT storage/ (cloned repos there would
    # otherwise trigger reloads mid-clone and 502 the Discovery request).
    uvicorn app.main:app --reload --reload-dir app --port $Port
}
