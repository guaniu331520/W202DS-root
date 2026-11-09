#!/system/bin/sh
# gms-enable module — early stage (post-fs-data)
# Flip ZTE's GMS-disable strategy flags OFF as early as possible.
# NOTE: The actual re-enable of the packages is done in service.sh, which
# Magisk runs at boot-COMPLETED. ZTE's disabler runs LATER than post-fs-data,
# so an enable done here would just get overwritten again.
LOG=/data/local/tmp/gms_enable.log
echo "=== gms-enable post-fs-data $(date) ===" >> "$LOG"

resetprop ro.vendor.feature.zte_strategy_disable_gms false 2>>"$LOG"
resetprop ro.vendor.feature.zte_feature_cgroup_gms_freezer false 2>>"$LOG"

echo "post-fs-data done" >> "$LOG"
