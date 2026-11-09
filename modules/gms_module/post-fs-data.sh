#!/system/bin/sh
# GMS Magisk module: relabel + fix perms for overlaid GMS files
LOG=/data/local/tmp/gms_module.log
echo "=== GMS post-fs-data $(date) ===" >> "$LOG"
for d in /product/app /product/priv-app /product/etc /product/lib /product/lib64 /product/overlay /product/framework /system_ext/priv-app /system_ext/etc; do
  restorecon -R "$d" 2>>"$LOG"
  find "$d" -type d -exec chmod 755 {} \; 2>/dev/null
  find "$d" -type f -exec chmod 644 {} \; 2>/dev/null
done
echo "GMS contexts/perms fixed" >> "$LOG"
