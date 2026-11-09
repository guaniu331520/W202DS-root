#!/system/bin/sh
# ADB root switch. Run from a terminal app that has been granted root:
#   su -c "sh /data/adb/modules/adbroot/toggle.sh"
# Flips the flag and applies immediately; reboot recommended so magiskd reloads config.
LOG=/data/local/tmp/adbroot_diag.txt
FLAG=/data/adb/adbroot/state
MAGISK=""
for i in $(seq 1 30); do
  for c in /system_ext/bin/magisk /system/bin/magisk; do
    if [ -x "$c" ] && "$c" -c >/dev/null 2>&1; then MAGISK="$c"; break 2; fi
  done
  sleep 1
done
[ -z "$MAGISK" ] && { echo "magisk not found"; exit 1; }
mkdir -p /data/adb/adbroot
[ -f "$FLAG" ] || echo on > "$FLAG"
cur=$(cat "$FLAG")
if [ "$cur" = "on" ]; then
  echo off > "$FLAG"
  "$MAGISK" --sqlite "DELETE FROM policies WHERE uid=2000;" 2>>"$LOG"
  for k in superuser_access su_access access su_policy superuser; do
    "$MAGISK" --sqlite "UPDATE settings SET value='1' WHERE key='$k';" 2>/dev/null
  done
  echo "ADB root is now OFF. Reboot to fully apply."
else
  echo on > "$FLAG"
  "$MAGISK" --sqlite "INSERT OR REPLACE INTO policies (uid,policy,until,logging,notification) VALUES (2000,1,0,1,1);" 2>>"$LOG"
  for k in superuser_access su_access access su_policy superuser; do
    "$MAGISK" --sqlite "UPDATE settings SET value='3' WHERE key='$k';" 2>/dev/null
  done
  echo "ADB root is now ON. Reboot to fully apply."
fi
