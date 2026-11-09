#!/system/bin/sh
# ADB Root Enabler — toggle-aware, no orphaned policy in Magisk DB.
# State file: /data/adb/adbroot/state  -> "on" grants adb (uid 2000) root, "off" revokes.
# Default: on (install => adb root). Flip off via toggle.sh or uninstall the module.
MODDIR=${0%/*}
LOG=/data/local/tmp/adbroot_diag.txt
FLAG=/data/adb/adbroot/state
MAGISK=""

# Robust detection: only accept a binary that ACTUALLY executes.
# /data/adb/magisk lives on a noexec mount -> must be excluded.
# /system_ext/bin/magisk only exists after /system_ext mounts (a bit after boot start) -> retry.
for i in $(seq 1 90); do
  for c in /system_ext/bin/magisk /system/bin/magisk; do
    if [ -x "$c" ] && "$c" -c >/dev/null 2>&1; then MAGISK="$c"; break 2; fi
  done
  sleep 1
done
[ -z "$MAGISK" ] && { echo "$(date) MAGISK NOT FOUND" >> "$LOG"; exit 1; }

mkdir -p /data/adb/adbroot
[ -f "$FLAG" ] || echo on > "$FLAG"
STATE=$(cat "$FLAG" 2>/dev/null)
[ "$STATE" = "on" ] || STATE=off

echo "=== $(date) boot state=$STATE magisk=$MAGISK ===" >> "$LOG"
"$MAGISK" --sqlite "SELECT key,value FROM settings;" >> "$LOG" 2>&1
"$MAGISK" --sqlite "SELECT * FROM policies;" >> "$LOG" 2>&1

set_access() {
  # $1 = value for the global superuser access switch (3 = apps+adb, 1 = apps only)
  for k in superuser_access su_access access su_policy superuser; do
    "$MAGISK" --sqlite "UPDATE settings SET value='$1' WHERE key='$k';" 2>/dev/null
  done
}

if [ "$STATE" = "on" ]; then
  "$MAGISK" --sqlite "INSERT OR REPLACE INTO policies (uid,policy,until,logging,notification) VALUES (2000,1,0,1,1);" 2>>"$LOG"
  set_access 3
  echo "RESULT: ENABLED" >> "$LOG"
else
  "$MAGISK" --sqlite "DELETE FROM policies WHERE uid=2000;" 2>>"$LOG"
  set_access 1
  echo "RESULT: DISABLED" >> "$LOG"
fi
"$MAGISK" --sqlite "SELECT * FROM policies;" >> "$LOG" 2>&1
