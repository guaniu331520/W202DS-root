# -*- coding: utf-8 -*-
"""Give the assistant time to deliver the final message, then suspend the PC (S3)."""
import ctypes
import datetime
import os
import time

LOG = r"C:\Users\Administrator\WorkBuddy\2026-11-07-21-28-02\flash-tools\overnight.log"
DELAY = 90


def note(msg):
    ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(LOG, "a", encoding="utf-8") as f:
        f.write("[%s] %s\n" % (ts, msg))


if __name__ == "__main__":
    note("Diagnosis finished. Report written. Suspending PC in %d seconds." % DELAY)
    time.sleep(DELAY)
    note("Triggering S3 sleep now.")
    try:
        ctypes.windll.powrprof.SetSuspendState(0, 1, 0)
        note("SetSuspendState returned.")
    except Exception as e:
        note("Sleep failed: %s" % e)
