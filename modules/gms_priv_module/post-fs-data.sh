#!/system/bin/sh
# gms_priv — promote factory GMS to a privileged system location.
# Strategy: build a tmpfs "stage" that contains the existing /product/priv-app
# apps PLUS the factory GMS apks (copied from /data/app, relabeled system_file),
# then bind-mount the stage over /product/priv-app. Also merge the privapp
# permissions allowlist into /product/etc/permissions via a second bind.
LOG=/data/local/tmp/gms_priv.log
echo "=== gms_priv post-fs-data $(date) ===" >> "$LOG"

STAGE=/data/local/tmp/gms_priv_stage
rm -rf "$STAGE" 2>/dev/null
mkdir -p "$STAGE"
if ! mount -t tmpfs tmpfs "$STAGE" 2>>"$LOG"; then
  echo "FATAL: tmpfs mount failed" >> "$LOG"
  exit 1
fi

# 1) Keep the existing real /product/priv-app apps working
cp -a /product/priv-app/. "$STAGE/" 2>>"$LOG"
echo "copied existing priv-app rc=$?" >> "$LOG"

# 2) Copy factory GMS apks into the stage and relabel as privileged system_file
CTX=u:object_r:system_file:s0
for pkg in com.android.vending com.google.android.gms com.google.android.gsf; do
  srcdir=$(ls -d /data/app/*/"${pkg}-"*/ 2>/dev/null | head -1)
  if [ -n "$srcdir" ]; then
    mkdir -p "$STAGE/$pkg"
    cp -a "$srcdir/." "$STAGE/$pkg/" 2>>"$LOG"
    chcon -R "$CTX" "$STAGE/$pkg" 2>>"$LOG"
    echo "$pkg <- $srcdir rc=$?" >> "$LOG"
  else
    echo "$pkg: NO SOURCE APK FOUND" >> "$LOG"
  fi
done

# 3) Permissions merge (existing + our google allowlist), relabeled
mkdir -p "$STAGE/permissions"
cp /product/etc/permissions/. "$STAGE/permissions/" 2>>"$LOG"
cp /data/adb/modules/gms_priv/privapp-permissions-google.xml "$STAGE/permissions/" 2>>"$LOG"
chcon -R "$CTX" "$STAGE/permissions" 2>>"$LOG"
echo "permissions merged rc=$?" >> "$LOG"

# 4) Relabel the whole stage, then bind over the real privileged paths
chcon -R "$CTX" "$STAGE" 2>>"$LOG"
mount --bind "$STAGE" /product/priv-app 2>>"$LOG"
echo "bind /product/priv-app rc=$?" >> "$LOG"
mount --bind "$STAGE/permissions" /product/etc/permissions 2>>"$LOG"
echo "bind /product/etc/permissions rc=$?" >> "$LOG"

# sanity: what does PM now see?
ls "$STAGE" >> "$LOG" 2>&1
echo "post-fs-data done" >> "$LOG"
