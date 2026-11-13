# GT-I9195 partition evidence comparison: 2026-11-13

Compared the existing 2026-11-10 PIT listing with read-only Android `/proc/partitions` and `by-name` reads on 2026-11-13. No new PIT transfer or partition read/write was performed.

The private 8,192-byte PIT still hashes to `1ec0d73501ca5b956b80b85583f9b578ea819e961e8fba3ccc1784b195f51432`. All 24 partition aliases match PIT identifiers; sizes match for all 23 fixed-size entries. USERDATA has a PIT count of zero (remainder); its observed Linux size is recorded, not inferred.

| PIT ID | PIT name | Start (512-byte sectors) | Count (512-byte sectors) | Observed alias / node | Linux 1 KiB blocks | Comparison |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | `MODEM` | 8,192 | 122,880 | `modem` / `mmcblk0p1` | 61,440 | PASS |
| 2 | `SBL1` | 131,072 | 256 | `sbl1` / `mmcblk0p2` | 128 | PASS |
| 3 | `SBL2` | 131,328 | 512 | `sbl2` / `mmcblk0p3` | 256 | PASS |
| 4 | `SBL3` | 131,840 | 1,024 | `sbl3` / `mmcblk0p4` | 512 | PASS |
| 5 | `ABOOT` | 132,864 | 4,096 | `aboot` / `mmcblk0p5` | 2,048 | PASS |
| 6 | `RPM` | 136,960 | 1,024 | `rpm` / `mmcblk0p6` | 512 | PASS |
| 7 | `TZ` | 137,984 | 1,024 | `tz` / `mmcblk0p7` | 512 | PASS |
| 8 | `PAD` | 139,008 | 25,600 | `pad` / `mmcblk0p8` | 12,800 | PASS |
| 9 | `PARAM` | 164,608 | 16,384 | `param` / `mmcblk0p9` | 8,192 | PASS |
| 10 | `EFS` | 180,992 | 27,904 | `efs` / `mmcblk0p10` | 13,952 | PASS |
| 11 | `MODEMST1` | 208,896 | 6,144 | `modemst1` / `mmcblk0p11` | 3,072 | PASS |
| 12 | `MODEMST2` | 215,040 | 6,144 | `modemst2` / `mmcblk0p12` | 3,072 | PASS |
| 13 | `BOOT` | 221,184 | 20,480 | `boot` / `mmcblk0p13` | 10,240 | PASS |
| 14 | `RECOVERY` | 241,664 | 20,480 | `recovery` / `mmcblk0p14` | 10,240 | PASS |
| 15 | `FOTA` | 262,144 | 20,480 | `fota` / `mmcblk0p15` | 10,240 | PASS |
| 16 | `BACKUP` | 282,624 | 14,320 | `backup` / `mmcblk0p16` | 7,160 | PASS |
| 17 | `FSG` | 296,944 | 6,144 | `fsg` / `mmcblk0p17` | 3,072 | PASS |
| 18 | `SSD` | 303,088 | 16 | `ssd` / `mmcblk0p18` | 8 | PASS |
| 19 | `PERSIST` | 303,104 | 16,384 | `persist` / `mmcblk0p19` | 8,192 | PASS |
| 20 | `PERSDATA` | 319,488 | 24,576 | `persdata` / `mmcblk0p20` | 12,288 | PASS |
| 21 | `SYSTEM` | 344,064 | 3,072,000 | `system` / `mmcblk0p21` | 1,536,000 | PASS |
| 22 | `CACHE` | 3,416,064 | 409,600 | `cache` / `mmcblk0p22` | 204,800 | PASS |
| 23 | `HIDDEN` | 3,825,664 | 73,728 | `hidden` / `mmcblk0p23` | 36,864 | PASS |
| 24 | `USERDATA` | 3,899,392 | 0 | `userdata` / `mmcblk0p24` | 5,685,231 | Alias confirmed; PIT remainder |
| 70 | `PGPT` | 0 | 34 | PIT pseudo-entry | n/a | Not a Linux partition |
| 71 | `PIT` | 34 | 16 | PIT pseudo-entry | n/a | Not a Linux partition |
| 72 | `MD5` | 50 | 32 | PIT pseudo-entry | n/a | Not a Linux partition |
| 73 | `SGPT` | 15,269,855 | 33 | PIT pseudo-entry | n/a | Not a Linux partition |

Whole disk: 15,269,888 sectors / 7,634,944 KiB. BOOT and RECOVERY each have 20,480 sectors / 10,485,760 bytes. The earlier draft estimate for USERDATA was 5,685,215 KiB; the observed result is 5,685,231 KiB and supersedes that estimate.

Sources: [Linux partitions](partitions.txt), [by-name links](by-name.txt). Original PIT and Heimdall logs remain private outside Git under `Tools/Heimdall-Evidence/GT-I9195-phase0/`. Protected boot-firmware, modem and identity partitions are inventory only and are never flashing targets.
