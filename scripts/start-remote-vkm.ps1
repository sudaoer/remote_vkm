<#
.SYNOPSIS
Uploads and builds the remote-vkm receiver on the board, starts it, then opens the local host capture client.

.EXAMPLE
.\scripts\start-remote-vkm.ps1

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -VerboseHost

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -ReceiverOnly

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -BoardHost bpi-f3 -BoardUser sudoer -SshAuth key

.EXAMPLE
.\scripts\start-remote-vkm.ps1 -BoardHost bpi-f3 -SshHost 192.168.1.39 -SshPort 22
#>

[CmdletBinding()]
param(
    [string]$BoardHost = "192.168.31.215",
    [string]$SshHost = "",
    [string]$BoardUser = "root",
    [int]$SshPort = 22,
    [ValidateSet("password", "key")]
    [string]$SshAuth = "password",
    [int]$Port = 5533,
    [string]$Listen = "0.0.0.0",
    [string]$RemoteRoot = "/tmp/remote-vkm-board",
    [string]$RemoteSource = "/tmp/remote-vkm-board/src/main.cpp",
    [string]$Receiver = "/tmp/remote-vkm-board/remote-vkm-receiver",
    [string]$RemoteLog = "/tmp/remote-vkm-board/receiver.log",
    [string]$LocalSource = "board/src/main.cpp",
    [string]$ClientHost = "",
    [ValidateSet("window", "global")]
    [string]$Capture = "window",
    [int]$SshConnectTimeout = 8,
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

function Resolve-IPv4OrFallback {
    param([string]$Name)

    $parsedAddress = $null
    if (
        [System.Net.IPAddress]::TryParse($Name, [ref]$parsedAddress) -and
        $parsedAddress.AddressFamily -eq [System.Net.Sockets.AddressFamily]::InterNetwork
    ) {
        return $Name
    }

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
    $hostArgs = @(
        "run", "host",
        "--host", $HostName,
        "--port", "$Port",
        "--capture", $Capture
    )
    if ($VerboseHost) {
        $hostArgs += "--verbose"
    }

    & pixi @hostArgs
    exit $LASTEXITCODE
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $repoRoot
Require-Command pixi

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

$localSourcePath = (Resolve-Path $LocalSource).Path
$remote = "$BoardUser@$resolvedBoardHost"
$knownHostsPath = Join-Path $repoRoot ".deploy_known_hosts"

if ($resolvedBoardHost -ne $BoardHost) {
    Write-Host "Resolved $BoardHost to $resolvedBoardHost"
}

Write-Host "Deploying receiver to ${remote}:$SshPort using $SshAuth authentication ..."
$deployArgs = @(
    "run", "python", "-m", "remote_vkm_host.deploy",
    "--host", $resolvedBoardHost,
    "--user", $BoardUser,
    "--ssh-port", "$SshPort",
    "--auth", $SshAuth.ToLowerInvariant(),
    "--connect-timeout", "$SshConnectTimeout",
    "--known-hosts", "$knownHostsPath",
    "--local-source", "$localSourcePath",
    "--remote-root", $RemoteRoot,
    "--remote-source", $RemoteSource,
    "--receiver", $Receiver,
    "--remote-log", $RemoteLog,
    "--listen", $Listen,
    "--receiver-port", "$Port"
)
if ($DryRunBoard) {
    $deployArgs += "--dry-run"
}

& pixi @deployArgs
if ($LASTEXITCODE -ne 0) {
    throw "Failed to deploy/start the remote receiver on $remote."
}

Write-Host "Waiting for receiver TCP port ${ClientHost}:${Port} ..."
$receiverReady = $false
for ($attempt = 0; $attempt -lt 20; $attempt++) {
    if (Test-ReceiverPort -HostName $ClientHost -Port $Port) {
        $receiverReady = $true
        break
    }
    Start-Sleep -Milliseconds 250
}
if (-not $receiverReady) {
    throw "Receiver deployment completed, but ${ClientHost}:${Port} did not become reachable."
}

if ($ReceiverOnly) {
    Write-Host "Receiver is ready. Skipping local capture because -ReceiverOnly was set."
    exit 0
}

Invoke-HostClient -HostName $ClientHost
