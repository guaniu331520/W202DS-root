#!/system/bin/sh
# gms-enable module — late stage (service.sh)
# Magisk runs this once at boot. ZTE's disabler (com.zte.heartyservice.strategy)
# turns off gms/gsf AFTER boot_completed, so a one-shot enable loses the race.
# We spawn a fully-detached watchdog (setsid) that keeps GMS enabled forever.
LOG=/data/local/tmp/gms_enable_svc.log
echo "=== gms-enable service.sh $(date) ===" >> "$LOG"

# setsid detaches the watchdog into its own session so magiskd cannot kill it
# when this script exits.
setsid sh -c '
  WLOG=/data/local/tmp/gms_enable_watch.log
  echo "watchdog start $(date)" >> "$WLOG"
  # wait until boot is fully completed
  for i in $(seq 1 120); do
    [ "$(getprop sys.boot_completed)" = "1" ] && break
    sleep 2
  done
  echo "watchdog: boot completed, entering loop" >> "$WLOG"
  while true; do
    n=$(pm list packages -d 2>/dev/null | grep -cE "com.google.android.gms|com.google.android.gsf|com.android.vending")
    if [ "$n" -gt 0 ]; then
      pm enable com.android.vending com.google.android.gms com.google.android.gsf >> "$WLOG" 2>&1
      echo "$(date) watchdog re-enabled ($n were disabled)" >> "$WLOG"
    fi
    sleep 20
  done
' &

echo "service.sh spawned watchdog, exiting" >> "$LOG"
