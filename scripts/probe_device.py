#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read-only pre-flight probe for ZTE W202DS.

Run this RIGHT AFTER an ADB channel is established (USB or wireless).
It changes nothing on the device: no settings writes, no partition writes.
It collects the facts you need before deciding how to root.

Usage:
    python3 probe_device.py                 # auto-find adb
    ADB=/path/to/adb python3 probe_device.py
    python3 probe_device.py > device-report.txt
"""
import os, shutil, subprocess, sys, pathlib, datetime

CANDIDATES = [
    os.environ.get('ADB', ''),
    shutil.which('adb') or '',
    str(pathlib.Path.cwd() / 'flash-tools' / 'platform-tools' / 'adb.exe'),
    str(pathlib.Path.cwd() / 'flash-tools' / 'platform-tools' / 'adb'),
]
ADB = next((c for c in CANDIDATES if c and pathlib.Path(c).exists()), None)
if not ADB:
    sys.exit('ERROR: adb not found. Set ADB=/path/to/adb or install platform-tools.')

PROPS = [
    'ro.product.brand', 'ro.product.model', 'ro.build.version.release',
    'ro.build.version.sdk', 'ro.build.display.id', 'ro.build.version.incremental',
    'ro.product.cpu.abi', 'ro.bootloader', 'ro.boot.slot_suffix',
    'ro.boot.flash.locked', 'ro.boot.vbmeta.device_state',
    'ro.boot.dynamic_partitions', 'ro.boot.veritymode', 'ro.secure',
    'ro.debuggable', 'sys.usb.config', 'sys.boot_completed',
]

SHELL_CMDS = [
    ('disabled packages (GMS)',
     "pm list packages -d 2>/dev/null | grep -iE 'vending|gms|gsf|aurora'"),
    ('google packages',
     "pm list packages 2>/dev/null | grep -iE 'vending|gms|gsf|aurora'"),
    ('erofs mounts', "cat /proc/mounts 2>/dev/null | grep erofs"),
    ('SELinux', 'getenforce'),
    ('adb_enabled', 'settings get global adb_enabled'),
    ('usb state', 'getprop sys.usb.state'),
    ('battery', "dumpsys battery 2>/dev/null | grep -i level"),
    ('storage', 'df -h /data 2>/dev/null'),
    ('root check', "su -c 'id' 2>/dev/null || echo 'no root yet'"),
]


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30)
        return (r.stdout + r.stderr).decode('utf-8', 'replace').strip()
    except Exception as e:
        return 'ERROR: %s' % e


def section(title):
    print('\n===== %s =====' % title)


print('W202DS device probe  %s' % datetime.datetime.now().isoformat(timespec='seconds'))
print('adb: %s' % ADB)
print('READ-ONLY: no settings changed, no partitions written.')

section('ADB DEVICES')
print(run([ADB, 'devices', '-l']))

section('KEY PROPERTIES')
for p in PROPS:
    print('%-32s = %s' % (p, run([ADB, 'shell', 'getprop', p])))

for title, cmd in SHELL_CMDS:
    section(title.upper())
    print(run([ADB, 'shell', cmd]) or '(empty)')

section('NEXT STEP')
print('If adb devices is EMPTY -> see README section 3.2 (USB GUID fix)')
print('If USB cannot be fixed  -> see README section 3.3 (wireless debugging)')
print('If BL is locked/erofs   -> see README section 5 (B route root)')
