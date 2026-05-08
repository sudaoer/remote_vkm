<#
.SYNOPSIS
Starts the remote-vkm receiver on bpi-f3 and then opens the local host capture client.

.EXAMPLE
.\scripts\start-remote-vkm.ps1

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -VerboseHost

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -BoardHost bpi-f3 -BoardUser sudoer -Port 5533

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -ReceiverOnly
#>

[CmdletBinding()]
param(
    [string]$BoardHost = "bpi-f3",
    [string]$BoardUser = "sudoer",
    [int]$Port = 5533,
    [string]$Listen = "0.0.0.0",
    [string]$Receiver = "/home/sudoer/remote_vkm/board/build/remote-vkm-receiver",
    [string]$RemoteLog = "/home/sudoer/remote_vkm/receiver.log",
    [string]$ClientHost = "",
    [ValidateSet("window", "global")]
    [string]$Capture = "window",
    [switch]$VerboseHost,
    [switch]$DryRunBoard,
    [switch]$ReceiverOnly
)

$ErrorActionPreference = "Stop"

function Require-Command {
    param([string]$Name)

    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' was not found in PATH."
    }
}

function Quote-Sh {
    param([string]$Value)

    return "'" + $Value.Replace("'", "'`"`"`'") + "'"
}

function Resolve-IPv4OrFallback {
    param([string]$Name)

    try {
        $record = Resolve-DnsName -Name $Name -Type A -ErrorAction Stop |
            Where-Object { $_.IPAddress } |
            Select-Object -First 1
        if ($record -and $record.IPAddress) {
            return $record.IPAddress
        }
    } catch {
        Write-Verbose "IPv4 DNS lookup for '$Name' failed: $($_.Exception.Message)"
    }

    return $Name
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

Require-Command ssh
Require-Command pixi

$remote = "$BoardUser@$BoardHost"
$receiverQ = Quote-Sh $Receiver
$logQ = Quote-Sh $RemoteLog
$listenQ = Quote-Sh $Listen
$dryRunArg = if ($DryRunBoard) { " --dry-run" } else { "" }

$remoteCommand = @"
set -eu
receiver=$receiverQ
log_file=$logQ
listen_addr=$listenQ
port=$Port

if [ ! -x "`$receiver" ]; then
    echo "receiver not found or not executable: `$receiver" >&2
    exit 2
fi

if ss -ltn "sport = :`$port" | grep -q LISTEN; then
    echo "remote-vkm receiver already listening on port `$port"
else
    mkdir -p "`$(dirname "`$log_file")"
    nohup sudo -n "`$receiver" --listen "`$listen_addr" --port "`$port"$dryRunArg > "`$log_file" 2>&1 < /dev/null &
    pid=`$!
    sleep 0.5
    if ! kill -0 "`$pid" 2>/dev/null; then
        echo "remote-vkm receiver failed to start; log follows:" >&2
        tail -n 80 "`$log_file" >&2 || true
        exit 1
    fi
    echo "started remote-vkm receiver pid=`$pid, log=`$log_file"
fi
"@

Write-Host "Starting receiver on $remote ..."
& ssh $remote $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Failed to start remote receiver on $remote."
}

if ($ReceiverOnly) {
    Write-Host "Receiver is ready. Skipping local capture because -ReceiverOnly was set."
    exit 0
}

if ([string]::IsNullOrWhiteSpace($ClientHost)) {
    $ClientHost = Resolve-IPv4OrFallback $BoardHost
}

Write-Host "Starting local capture client -> ${ClientHost}:${Port} ..."
$hostArgs = @("run", "host", "--host", $ClientHost, "--port", "$Port", "--capture", $Capture)
if ($VerboseHost) {
    $hostArgs += "--verbose"
}

& pixi @hostArgs
exit $LASTEXITCODE
