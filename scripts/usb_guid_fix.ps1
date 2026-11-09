# usb_guid_fix.ps1 - repair Windows ADB enumeration for ZTE W202DS
#
# Symptom: USB debugging is ON, MTP is selected, Windows shows an
# "ADB Interface" with a working WinUSB driver, but `adb devices` is EMPTY
# (not even "unauthorized") and the "Allow USB debugging?" dialog never
# appears on the tablet.
#
# Root cause: the generic WinUSB driver did not register the ADB interface
# GUID {F72FE0D4-CBCB-407D-8814-9ED673D0DD6B} in DeviceInterfaceGUIDs.
# adb.exe's AdbWinUsbApi.dll enumerates devices by that GUID, so it cannot
# see the interface -> no handshake -> no authorization prompt.
#
# Run as Administrator in Windows PowerShell. The change is reversible;
# this script backs up the original values first.
#
# Alternative (no registry editing): install Google USB Driver with the
# VID_19D2&PID_0306 line added, or use Zadig / Universal ADB Driver.

$ErrorActionPreference = 'Continue'
$GUID = '{F72FE0D4-CBCB-407D-8814-9ED673D0DD6B}'
$BASE = 'HKLM:\SYSTEM\CurrentControlSet\Enum\USB\VID_19D2&PID_0306&MI_01'

if (-not (Test-Path $BASE)) {
  'ERROR: device not found at ' + $BASE
  'Plug the tablet in, set USB mode to File Transfer (MTP), then retry.'
  exit 1
}

function Get-Instances {
  Get-ChildItem $BASE | ForEach-Object { $_ }
}

'--- 1) current state ---'
$instances = @(Get-Instances)
foreach ($i in $instances) {
  $dp = Join-Path $i.PSPath 'Device Parameters'
  $v  = (Get-ItemProperty $dp -ErrorAction SilentlyContinue).DeviceInterfaceGUIDs
  'INSTANCE: {0}  DeviceInterfaceGUIDs: {1}' -f $i.PSChildName, $(if ($v) { $v } else { '(NOT SET)' })
}

'--- 2) backup ---'
$stamp  = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup = Join-Path (Get-Location) ("usb_guid_backup-$stamp.json")
$snap = @()
foreach ($i in $instances) {
  $dp = Join-Path $i.PSPath 'Device Parameters'
  $v  = (Get-ItemProperty $dp -ErrorAction SilentlyContinue).DeviceInterfaceGUIDs
  $snap += [pscustomobject]@{ instance = $i.PSChildName; value = $v }
}
$snap | ConvertTo-Json -Depth 4 | Out-File $backup -Encoding utf8
'Backup saved: ' + $backup

'--- 3) register the ADB interface GUID (REG_MULTI_SZ) ---'
foreach ($i in $instances) {
  $dp = Join-Path $i.PSPath 'Device Parameters'
  try {
    New-ItemProperty -Path $dp -Name 'DeviceInterfaceGUIDs' -Value @($GUID) `
      -PropertyType MultiString -Force | Out-Null
    'SET: ' + $i.PSChildName
  } catch {
    'FAIL: ' + $i.PSChildName + ' -> ' + $_.Exception.Message
  }
}

'--- 4) re-enumerate device and restart adb ---'
try {
  Get-PnpDevice | Where-Object { $_.InstanceId -like '*VID_19D2&PID_0306*' } | ForEach-Object {
    Disable-PnpDevice -InstanceId $_.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
    Enable-PnpDevice  -InstanceId $_.InstanceId -Confirm:$false -ErrorAction SilentlyContinue
  }
} catch { 'Re-enumeration skipped: ' + $_.Exception.Message }

$adb = (Get-Command adb -ErrorAction SilentlyContinue).Source
if ($adb) {
  & $adb kill-server 2>$null
  & $adb start-server 2>$null
  '--- 5) adb devices ---'
  & $adb devices
} else {
  'adb not on PATH; run: <platform-tools>\adb.exe kill-server && adb devices'
}
'Now look at the tablet screen: the "Allow USB debugging?" dialog should appear.'
