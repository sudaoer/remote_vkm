<#
.SYNOPSIS
Uploads and builds the remote-vkm receiver on the board, starts it, then opens the local host capture client.

.EXAMPLE
.\scripts\start-remote-vkm.ps1

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -VerboseHost

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -BoardHost bpi-f3 -BoardUser sudoer -Port 5533

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -BoardHost bpi-f3 -SshHost 192.168.1.39

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -ReceiverOnly
#>

[CmdletBinding()]
param(
    [string]$BoardHost = "k3-pico-itx",
    [string]$SshHost = "",
    [string]$BoardUser = "sudoer",
    [int]$Port = 5533,
    [string]$Listen = "0.0.0.0",
    [string]$RemoteRoot = "/home/sudoer/remote_vkm",
    [string]$RemoteSource = "/home/sudoer/remote_vkm/board/src/main.cpp",
    [string]$Receiver = "/home/sudoer/remote_vkm/board/remote-vkm-receiver",
    [string]$RemoteLog = "/home/sudoer/remote_vkm/receiver.log",
    [string]$LocalSource = "board/src/main.cpp",
    [string]$ClientHost = "",
    [ValidateSet("window", "global")]
    [string]$Capture = "window",
    [int]$SshConnectTimeout = 8,
    [int]$ReconnectAttempts = 5,
    [double]$ReconnectDelay = 1.0,
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

    $names = @($Name)
    if (-not $Name.EndsWith(".local", [System.StringComparison]::OrdinalIgnoreCase)) {
        $names += "$Name.local"
    }

    foreach ($candidate in $names) {
        try {
            $record = Resolve-DnsName -Name $candidate -Type A -ErrorAction Stop |
                Where-Object { $_.IPAddress } |
                Select-Object -First 1
            if ($record -and $record.IPAddress) {
                return $record.IPAddress
            }
        } catch {
            Write-Verbose "IPv4 DNS lookup for '$candidate' failed: $($_.Exception.Message)"
        }
    }

    Write-Warning "Could not resolve an IPv4 address for '$Name'; falling back to the original host string."
    return $Name
}

function Test-ReceiverPort {
    param(
        [string]$HostName,
        [int]$Port
    )

    if (Get-Command Test-NetConnection -ErrorAction SilentlyContinue) {
        try {
            return [bool](Test-NetConnection -ComputerName $HostName -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue)
        } catch {
            Write-Verbose "TCP probe for ${HostName}:${Port} failed: $($_.Exception.Message)"
            return $false
        }
    }

    Write-Verbose "Test-NetConnection was not found; using TcpClient fallback."
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync($HostName, $Port)
        if (-not $task.Wait(1000)) {
            return $false
        }
        return $client.Connected
    } catch {
        Write-Verbose "TCP probe for ${HostName}:${Port} failed: $($_.Exception.Message)"
        return $false
    } finally {
        $client.Dispose()
    }
}

function Invoke-HostClient {
    param([string]$HostName)

    Require-Command pixi

    Write-Host "Starting local capture client -> ${HostName}:${Port} ..."
    $reconnectDelayText = $ReconnectDelay.ToString([System.Globalization.CultureInfo]::InvariantCulture)
    $hostArgs = @(
        "run", "host",
        "--host", $HostName,
        "--port", "$Port",
        "--capture", $Capture,
        "--reconnect-attempts", "$ReconnectAttempts",
        "--reconnect-delay", $reconnectDelayText
    )
    if ($VerboseHost) {
        $hostArgs += "--verbose"
    }

    & pixi @hostArgs
    exit $LASTEXITCODE
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot

if ($ReconnectAttempts -lt 0) {
    throw "ReconnectAttempts must be greater than or equal to 0."
}
if ($ReconnectDelay -lt 0) {
    throw "ReconnectDelay must be greater than or equal to 0."
}

$resolvedBoardHost = ""
if ([string]::IsNullOrWhiteSpace($ClientHost)) {
    $resolvedBoardHost = if ([string]::IsNullOrWhiteSpace($SshHost)) { Resolve-IPv4OrFallback $BoardHost } else { $SshHost }
    $ClientHost = $resolvedBoardHost
}

Write-Host "Probing receiver TCP port ${ClientHost}:${Port} ..."
if (Test-ReceiverPort -HostName $ClientHost -Port $Port) {
    Write-Host "Receiver already listening on ${ClientHost}:${Port}; skipping remote build/start."
    if ($ReceiverOnly) {
        Write-Host "Receiver is ready. Skipping local capture because -ReceiverOnly was set."
        exit 0
    }
    Invoke-HostClient -HostName $ClientHost
}

if ([string]::IsNullOrWhiteSpace($resolvedBoardHost)) {
    $resolvedBoardHost = if ([string]::IsNullOrWhiteSpace($SshHost)) { Resolve-IPv4OrFallback $BoardHost } else { $SshHost }
}

Require-Command ssh
Require-Command scp

$localSourcePath = (Resolve-Path $LocalSource).Path
$remote = "$BoardUser@$resolvedBoardHost"
$remoteRootQ = Quote-Sh $RemoteRoot
$remoteSourceQ = Quote-Sh $RemoteSource
$receiverQ = Quote-Sh $Receiver
$logQ = Quote-Sh $RemoteLog
$listenQ = Quote-Sh $Listen
$dryRunArg = if ($DryRunBoard) { " --dry-run" } else { "" }
$sshOptions = @(
    "-o", "BatchMode=yes",
    "-o", "ConnectTimeout=$SshConnectTimeout",
    "-o", "StrictHostKeyChecking=accept-new"
)

$prepareCommand = @"
set -eu
mkdir -p $remoteRootQ
mkdir -p "`$(dirname $remoteSourceQ)"
mkdir -p "`$(dirname $receiverQ)"
"@

if ($resolvedBoardHost -ne $BoardHost) {
    Write-Host "Resolved $BoardHost to $resolvedBoardHost"
}

Write-Host "Preparing remote build directory on $remote ..."
& ssh @sshOptions $remote $prepareCommand
if ($LASTEXITCODE -ne 0) {
    throw "Failed to prepare remote build directory on $remote."
}

Write-Host "Uploading board source to ${remote}:${RemoteSource} ..."
& scp @sshOptions "$localSourcePath" "${remote}:${RemoteSource}"
if ($LASTEXITCODE -ne 0) {
    throw "Failed to upload board source to $remote."
}

$remoteCommand = @"
set -eu
source_file=$remoteSourceQ
receiver=$receiverQ
log_file=$logQ
listen_addr=$listenQ
port=$Port

if ! command -v c++ >/dev/null 2>&1; then
    echo "required compiler 'c++' was not found on target host" >&2
    exit 2
fi

if [ ! -f "`$source_file" ]; then
    echo "source file not found: `$source_file" >&2
    exit 2
fi

echo "building remote-vkm receiver with c++"
tmp_receiver="`$receiver.new"
c++ -std=c++17 -O2 -Wall -Wextra -Wpedantic -o "`$tmp_receiver" "`$source_file"
chmod +x "`$tmp_receiver"
mv -f "`$tmp_receiver" "`$receiver"

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
& ssh @sshOptions $remote $remoteCommand
if ($LASTEXITCODE -ne 0) {
    throw "Failed to start remote receiver on $remote."
}

if ($ReceiverOnly) {
    Write-Host "Receiver is ready. Skipping local capture because -ReceiverOnly was set."
    exit 0
}

Invoke-HostClient -HostName $ClientHost
