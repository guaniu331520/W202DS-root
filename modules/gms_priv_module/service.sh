#!/system/bin/sh
# gms_priv — late stage.
# After boot, confirm the privileged (bind-mounted) GMS is what PackageManager
# sees. If so, remove the leftover /data/app copies so the privileged system
# version is the active one (otherwise the unprivileged /data copy shadows it).
LOG=/data/local/tmp/gms_priv_svc.log
echo "=== gms_priv service.sh $(date) ===" >> "$LOG"

for i in $(seq 1 60); do
  [ "$(getprop sys.boot_completed)" = "1" ] && break
  sleep 2
done

# Only act if our bind mount is actually in place
if [ -e /product/priv-app/com.google.android.gms ]; then
  echo "priv-app GMS present, removing /data copies" >> "$LOG"
  for pkg in com.android.vending com.google.android.gms com.google.android.gsf; do
    # pm uninstall removes only the /data install, leaving the system (privileged) one
    out=$(pm uninstall "$pkg" 2>&1)
    echo "$pkg: $out" >> "$LOG"
  done
else
  echo "priv-app GMS NOT present (bind failed) — keeping /data fallback" >> "$LOG"
fi

echo "service.sh done" >> "$LOG"
