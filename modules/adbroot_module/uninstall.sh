#!/system/bin/sh
# Runs as root when the module is uninstalled. Must leave the Magisk DB clean.
LOG=/data/local/tmp/adbroot_diag.txt
MAGISK=""
for i in $(seq 1 30); do
  for c in /system_ext/bin/magisk /system/bin/magisk; do
    if [ -x "$c" ] && "$c" -c >/dev/null 2>&1; then MAGISK="$c"; break 2; fi
  done
  sleep 1
done
if [ -n "$MAGISK" ]; then
  "$MAGISK" --sqlite "DELETE FROM policies WHERE uid=2000;" 2>>"$LOG"
  for k in superuser_access su_access access su_policy superuser; do
    "$MAGISK" --sqlite "UPDATE settings SET value='1' WHERE key='$k';" 2>/dev/null
  done
  echo "$(date) UNINSTALL: revoked adb root, DB cleaned" >> "$LOG"
fi
rm -f /data/adb/adbroot/state
