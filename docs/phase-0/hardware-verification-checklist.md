# Phase 0 hardware verification checklist: GT-I9195 on Ubuntu

**Purpose:** confirm the exact phone, its firmware, and its boot, recovery and Download-mode paths, **without writing anything to the phone**. This is a **one-time stock-hardware baseline and rescue assessment**, not a recurring requirement to boot Android. From Phase 2 onward, boot and reboot milestones must exercise **Revival OS code**. The owner intends to remove Android and does not require preserving personal files. This is the observable test for [Phase 0](../../ROADMAP.md#phase-0--samsung-identification-boot-reboot-and-recovery). The research behind each step is in [gt-i9195.md](../hardware/gt-i9195.md).

**Status:** not yet performed. No result has been recorded.

**Time needed:** about 2–3 hours, plus downloading the stock firmware (section G).

## Rules for this checklist

### Allowed

- **adb (read-only):** `adb devices`, `adb shell getprop`, `adb shell cat` of `/proc` and `/sys` files, `adb shell ls`, `adb shell dumpsys battery`, `adb shell ip`, `adb logcat -d`, `adb pull`, `adb reboot` (with no argument), `adb wait-for-device`.
- **Heimdall (read-only):** `heimdall version`, `heimdall help`, `heimdall detect`, `heimdall print-pit`, `heimdall download-pit`.
- **Ubuntu:** `lsusb`, `journalctl -k`, `ping`, `file`, `sha256sum`, `md5sum`, `tar -tvf`.
- **On the phone:** the stock menus named in each step.

### Forbidden in Phase 0

- `heimdall flash`, Odin, any `fastboot` command, `dd`, or any flashing app.
- Root, `su`, `adb root`, `adb remount`, rooting apps or exploits, or `adb push` to anything but `/sdcard`.
- Recovery menu actions other than **reboot system now**: no wipe, no factory reset, no "apply update".
- Accepting a system software update. Updating changes the build that the stock firmware must match.
- Removing the battery **during** a transfer. This checklist never starts a transfer.

### Stop at once and report if

- the label or software says anything other than **GT-I9195** (for example GT-I9195I, GT-I9190 or GT-I9192);
- the battery is swollen, leaking or hot;
- any screen asks you to confirm an erase, wipe, update or flash;
- the phone shows an error such as "Firmware upgrade encountered an issue";
- Android stops booting normally;
- a command prints something this checklist does not describe and you are unsure what it means.

Stopping costs nothing. Guessing can.

### Privacy

The IMEI, serial numbers (`ro.serialno`, `androidboot.serialno` in `/proc/cmdline`, the USB serial), Wi-Fi and Bluetooth MAC addresses, account names and personal photos must **not** be committed. Save everything to the private evidence directory (A2). Only the redacted summary (H2) goes into the repository.

---

## A. Preparation (phone not connected)

**A1. Install the Phase 0 tools (one time, about 3 MB).** On the development machine these were installed on 2026-11-08; `make doctor` shows their versions.

```sh
sudo apt install adb heimdall-flash android-sdk-platform-tools-common
adb version
heimdall version
```

Record both version lines. `android-sdk-platform-tools-common` installs the udev rules that give your user access to Android USB devices. If Heimdall later reports a USB access error, the read-only Heimdall commands in this checklist may be run with `sudo`.

**A2. Create the private evidence directory and record the session.**

```sh
export EV="$HOME/revival-evidence/gt-i9195/phase-0/$(date +%F)"
mkdir -p "$EV/private"
cd "$EV"
script -q -a "$EV/private/session.log"     # records everything typed and printed; type exit to stop
```

Keep this directory outside every Git repository. Set `EV` again (first line) in any new terminal.

**A3. Record the USB devices before the phone is connected.**

```sh
lsusb > "$EV/A3-lsusb-before.txt"
```

**A4. Read the [rules](#rules-for-this-checklist) above.** Record the date, time and who performed the steps.

## B. Physical inspection (phone powered off)

**B1. Model label.** Remove the back cover and the battery. Read the label under the battery.

- Record: the model number exactly as printed, including any suffix such as `L`, `T` or `I`.
- Photograph it to `$EV/private/` and cover the IMEI and serial before sharing.
- **Pass:** the model reads `GT-I9195`. **Stop** for anything else.

**B2. Battery condition.** Lay the battery flat on a table. It must not rock, bulge or show leakage or heat.

- Record the battery's model and capacity from its label.
- **Stop** if it is swollen or damaged. Do not charge it.

**B3. Charge.** Reinsert the battery and charge the phone to **at least 60 %** with a known-good USB **data** cable (not a charge-only cable). Use the same cable for every step.

**B4. Cards.** Record whether a SIM card and a microSD card are inserted, and the microSD size. Leave them as they are.

## C. Stock Android baseline (one-time diagnostics only)

**C1. Software identity.** Power on normally. Open Settings → About device (the menu name varies by version) and record:

- Model number
- Android version
- Baseband version
- Kernel version
- Build number
- Any Knox or SE for Android lines

Take a photo or screenshot (Power + Home) to `$EV/private/`.

**C2. Stock cold boot timing, 3 trials (diagnostic baseline only).** These stock boots are not evidence that Revival OS boots. For each trial:

1. Hold Power, then choose Power off.
2. Wait 10 seconds.
3. Start a stopwatch as you press Power.
4. Stop it when the lock screen appears.

- Record the three times.
- **Pass:** 3 of 3 boots reach the lock screen.

**C3. Enable USB debugging.** Settings → About device → tap **Build number** seven times. Then Settings → Developer options → enable **USB debugging**.

**C4. ADB authorization, with its negative test.** Connect the phone to Ubuntu. **Before** accepting the prompt on the phone, run:

```sh
adb devices -l | tee "$EV/C4-adb-before-authorizing.txt"
```

- **Expected (negative test):** the phone is listed as `unauthorized`.

Now accept the RSA prompt on the phone and run:

```sh
adb devices -l | tee "$EV/C4-adb-after-authorizing.txt"
```

- **Expected:** the phone is listed as `device`.

**C5. Identity, CPU, memory and partitions (read-only).**

```sh
for p in ro.product.model ro.product.device ro.product.name ro.product.board \
         ro.board.platform ro.bootloader ro.build.fingerprint ro.build.version.release \
         ro.build.display.id gsm.version.baseband ro.csc.sales_code ro.boot.warranty_bit \
         ro.warranty_bit ro.boot.debug_level ro.secure ro.debuggable; do
  printf '%s=%s\n' "$p" "$(adb shell getprop "$p" | tr -d '\r')"
done | tee "$EV/C5-getprop-selected.txt"

adb shell cat /proc/cpuinfo   | tee "$EV/C5-cpuinfo.txt"
adb shell cat /proc/meminfo   | head -5 | tee "$EV/C5-meminfo.txt"
adb shell cat /proc/version   | tee "$EV/C5-proc-version.txt"
adb shell cat /proc/partitions | tee "$EV/C5-partitions.txt"
adb shell ls -l /dev/block/platform/msm_sdcc.1/by-name/ | tee "$EV/C5-by-name.txt"

# Private: these contain serial numbers.
adb shell getprop          > "$EV/private/C5-getprop-all.txt"
adb shell cat /proc/cmdline > "$EV/private/C5-cmdline.txt"
```

Expected, from the research (record what you **actually** see):

- `ro.product.model` is `GT-I9195`.
- `ro.bootloader` begins `I9195`.
- `ro.board.platform` is probably `msm8960`.
- `/proc/cpuinfo` shows an ARMv7 processor, two processors, and `CPU implementer : 0x51` (Qualcomm). Record the `Features` line (VFP, NEON, integer divide) and the `Hardware` line.
- `MemTotal` is somewhat under 1.5 GB.
- `by-name` lists at least `boot`, `recovery`, `system`, `userdata`, `cache`, `efs`, `persist`, `modem` and `fota`, and probably bootloader-chain partitions too.

If a command prints `Permission denied`, record that. Do not try to work around it.

**C6. Rear camera sensor.** Samsung kernels often expose the sensor type in sysfs. These paths are **unverified** for this model:

```sh
adb shell ls /sys/class/camera/ 2>&1 | tee "$EV/C6-camera-sysfs.txt"
for f in rear/rear_camtype rear/rear_camfw front/front_camtype front/front_camfw; do
  printf '%s: %s\n' "$f" "$(adb shell cat /sys/class/camera/$f 2>&1 | tr -d '\r')"
done | tee -a "$EV/C6-camera-sysfs.txt"
```

If these are absent, open the camera app on the phone, then run:

```sh
adb logcat -d | grep -iE 'imx175|s5k3h5|s5k6a3|sensor' | tail -50 | tee "$EV/C6-camera-logcat.txt"
```

- Record which rear sensor is named: `IMX175`, `S5K3H5XA`, or not determinable.

**C7. Wi-Fi baseline.** Connect the phone to your home Wi-Fi.

```sh
adb shell ip addr show wlan0 > "$EV/private/C7-wlan0.txt"       # contains the MAC address
adb shell ip -4 addr show wlan0 | grep inet | tee "$EV/C7-ip.txt"
ping -c 20 <phone-ip-from-C7-ip.txt> | tee "$EV/C7-ping.txt"
```

- Record the band (2.4 or 5 GHz) if Settings or the router shows it.
- **Pass:** 20 replies with little or no loss.

**C8. Camera baseline.** With the stock camera app, aim at a neutral scene (no people, no identifying details). Take:

- a rear photo,
- a 10-second rear video,
- a front photo,
- a 10-second front video.

Then:

```sh
adb shell ls -l /sdcard/DCIM/Camera/ | tail -8 | tee "$EV/C8-camera-files.txt"
mkdir -p "$EV/private/camera"
adb pull /sdcard/DCIM/Camera/<photo-or-video-file> "$EV/private/camera/"    # repeat for the 4 new files
file "$EV/private/camera/"* | tee "$EV/C8-camera-file-types.txt"
```

- Record the photo resolutions and the video resolution and frame rate set in the camera app.

**C9. Buttons, display and battery.**

- Press Volume Up, Volume Down, Home and Power, and touch the two capacitive keys beside Home. Record that each responds.
- Look for dead pixels or burn-in on the display (it is AMOLED) and record what you find.

```sh
adb shell dumpsys battery | tee "$EV/C9-battery.txt"
```

- Record the level, health, temperature and voltage.

**C10. Stock ADB reboot, 3 trials (diagnostic baseline only).** After Phase 0, reboot milestones must test the Revival OS image, not Android.

```sh
for i in 1 2 3; do
  echo "trial $i start $(date +%T)"
  adb reboot
  adb wait-for-device
  until [ "$(adb shell getprop sys.boot_completed 2>/dev/null | tr -d '\r')" = 1 ]; do sleep 2; done
  echo "trial $i booted $(date +%T)"
done | tee "$EV/C10-reboots.txt"
```

- **Pass:** 3 of 3 boots complete.

**C11. USB identity in Android mode.**

```sh
lsusb | grep -i 04e8 | tee "$EV/C11-lsusb-android.txt"
```

- Record the vendor:product ID. Do not save `lsusb -v`; it prints the serial number.

**C12. Heimdall negative test (phone still in Android).**

```sh
heimdall detect; echo "exit=$?"
```

Save the output as `$EV/C12-heimdall-detect-android.txt`.

- **Expected:** Heimdall finds no download-mode device and exits non-zero.

## D. Personal data (owner's decision)

**D1.** The owner has designated this phone for experiments and has no requirement to preserve its personal data. Phase 0 still performs no erase or write. A backup is optional and not a pass criterion. If you choose to copy files, keep them **outside** the evidence directory and every repository. For example:

```sh
adb pull /sdcard/DCIM "$HOME/phone-backup/gt-i9195/DCIM"
```

- Record only whether a backup was made, not its contents.

## E. Stock recovery mode (3 trials)

**E1.** For each trial:

1. Power off.
2. Hold **Volume Up + Home + Power**.
3. When the Samsung logo appears, release **Power** only, and keep holding Volume Up + Home until the recovery menu appears. If Android boots instead, power off and try again.
4. Photograph the menu and any text at its top or bottom to `$EV/private/`. Transcribe the header (for example "Android system recovery") and any build string.
5. **Do not select** any wipe, factory reset or "apply update" item. Use the volume keys to highlight **reboot system now**, then press Power.
6. Confirm that the current stock firmware boots. This is a Phase 0 diagnostic, **not** a requirement to preserve Android or inspect personal files.

If the screen shows only an Android robot and no menu for 30 seconds, remove the battery, reinsert it and power on normally.

- **Pass:** 3 of 3 diagnostic trials enter stock recovery, leave it with **reboot system now**, and boot the existing stock firmware. Personal-data checks are not required.

## F. Download mode

**F1. The cancel path, 3 trials (negative test).** For each trial:

1. Power off.
2. Hold **Volume Down + Home + Power** until a warning screen appears, then release.
3. On the first trial, photograph the warning and transcribe it.
4. Press **Volume Down** (cancel).

- **Expected:** the phone restarts into Android.
- **Pass:** 3 of 3.

**F2. Enter Download mode and read its status lines.**

1. Power off.
2. Hold Volume Down + Home + Power until the warning screen appears.
3. Press **Volume Up** (continue).
4. The phone shows a download screen, typically "Downloading… Do not turn off target". Nothing is being downloaded.
5. Photograph the small text at the top left clearly, and **transcribe every line exactly** into `$EV/F2-download-mode-lines.txt`.

The lines may include product name, current binary, system status, reactivation lock, Knox kernel lock, Knox warranty void, Qualcomm secure boot and write protection. Record what is shown, whatever it is.

- **Stop** if `REACTIVATION LOCK` is `ON` and you do not know the Samsung account.

**F3. USB identity in Download mode.** Connect the USB cable if it is not connected.

```sh
lsusb | grep -i 04e8 | tee "$EV/F3-lsusb-download.txt"
journalctl -k --since "-3 min" | tail -30 | tee "$EV/F3-kernel-log.txt"
```

- Record the vendor:product ID. It differs from C11.

**F4. Heimdall detection.**

```sh
heimdall detect 2>&1 | tee "$EV/F4-heimdall-detect.txt"
```

- **Expected:** `Device detected`.

**F5. Read the partition table (PIT). Read-only.** These are the **only** Heimdall commands besides `detect`, `version` and `help` allowed in Phase 0.

```sh
heimdall print-pit --no-reboot 2>&1 | tee "$EV/F5-print-pit.txt"
heimdall download-pit --output "$EV/private/F5-device.pit" --no-reboot --resume 2>&1 | tee "$EV/F5-download-pit.txt"
sha256sum "$EV/private/F5-device.pit" | tee "$EV/F5-pit-sha256.txt"
```

The Heimdall manual states that after a command with `--no-reboot`, the next command must include `--resume`. That is why the second command has it.

- Record every partition name, identifier and block count from `F5-print-pit.txt`.
- PIT names may differ from the `by-name` names in C5 (for example in case, or the modem firmware partition under a different name). Map them using the partition order and sizes, and mark any mapping that is uncertain.
- **Pass:** the PIT reads completely and lists boot and recovery partitions.

If a command hangs for more than 2 minutes, remove the battery (no transfer is running) and record what happened.

**F6. Leave Download mode by removing the battery, 3 trials.** This proves a physical emergency exit path; these returns to the existing stock baseline are not Revival OS boot/reboot milestones.

1. With Download mode idle (no command running), remove the battery for 10 seconds.
2. Reinsert it and power on normally.
3. Confirm Android boots.

The session after F2–F5 is trial 1. Repeat F2 steps 1–3, then this step, twice more.

- **Pass:** 3 of 3 trials boot Android normally.

## G. Restore source (no flashing)

**G1. Exact build identifiers.** From C1 and C5, record:

- the build (the PDA/AP version in `ro.build.display.id` or the build number, for example of the form `I9195XX…`),
- the bootloader version (`ro.bootloader`),
- the baseband,
- the CSC or region code (`ro.csc.sales_code`, if present).

**G2. Obtain the matching stock firmware.** Find the firmware for exactly this model, build and region from a source the reviewer accepts (Samsung's update service through an established client, or an established firmware archive). Do not use a different build or a different model.

- Record the source, the file name and the size.
- Never commit firmware. It is proprietary and large.

**G3. Verify it.** Samsung firmware of this era is usually a `.tar.md5` file: a tar archive with its MD5 line appended (Community-documented format).

```sh
f="<path>/<firmware>.tar.md5"
tail -n 1 "$f"                                        # the recorded MD5 and file name
head -c -"$(tail -n 1 "$f" | wc -c)" "$f" | md5sum    # MD5 of the archive part
tar -tvf "$f" | tee "$EV/G3-firmware-contents.txt"
sha256sum "$f" | tee "$EV/G3-firmware-sha256.txt"
```

- **Pass:** the two MD5 values are equal, and the listing contains `boot.img` and `recovery.img`.
- Also record the other files it contains. Bootloader images such as `sbl1.mbn` or `aboot.mbn` are listed for the record and are **never** flashed by Revival work.
- If the format differs, or the MD5 values differ, **stop** and report.

**G4. Store it privately.** Keep the firmware outside every repository, for example in `~/revival-firmware/gt-i9195/<build>/`, with the `sha256sum` output beside it. Do not flash it.

## H. Close-out

**H1. Final Phase 0 baseline check.** Power on the existing stock firmware and confirm:

- `adb shell getprop ro.build.fingerprint` equals the value in `C5-getprop-selected.txt`;
- Wi-Fi reconnects, or record why that diagnostic check cannot be completed.

Do **not** test preservation of personal photos or files; the owner has declared these disposable. This stock boot is **not** a future Revival OS boot/reboot acceptance criterion.

**H2. Evidence summary.** Copy the template from [docs/TESTING.md](../TESTING.md#phase-0-summary-template), fill it in from the `$EV` files, and **redact** identifiers. Include the text outputs that are free of identifiers.

**H3. Decide.** Compare the results with the [Phase 0 pass and fail criteria](../../ROADMAP.md#phase-0--samsung-identification-boot-reboot-and-recovery). Write PASS, PASS WITH BLOCKERS (list them) or FAIL.

**H4. Report.** Open a pull request in this repository adding the redacted summary under `docs/evidence/phase-0/`. Record in it that no write was performed. The orchestrator reviews it. Phase 2's write plan is a separate decision and is not part of this pull request.

## Step index

| Step | What it confirms | Writes to the phone |
| --- | --- | --- |
| A1–A4 | Tools, evidence directory, rules | No |
| B1–B4 | Model label, battery, charge, cards | No |
| C1–C12 | Software identity, boot and reboot, ADB, CPU, memory, partitions, camera sensor, Wi-Fi, camera, buttons, display, battery, USB ID, Heimdall negative test | No |
| D1 | Optional personal backup | No |
| E1 | Stock recovery entry and exit | No |
| F1–F6 | Download-mode cancel path, status lines, USB ID, Heimdall detect, PIT read, exit by battery removal | No (read-only protocol commands) |
| G1–G4 | Matching stock firmware identified and verified | No |
| H1–H4 | Final state, evidence summary, decision, report | No |
