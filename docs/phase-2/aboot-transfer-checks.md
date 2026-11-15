# What the stock bootloader (aboot) checks at transfer and at start

**Draft, for the reviewer.** Task R-2 P3, corrected in the R-3 second pass. Host-only study; nothing touched the phone. No part of the firmware and no disassembly listing is in this file.

> **Correction (R-3 second pass).** The first version of this note made four claims that this pass found wrong or unproven and corrects below: (1) it said `0x88e0c048` "sets the Knox warranty bit"; it is a **coloured display print** (`0xff0000` is red text). (2) it gave no condition for `SECURE CHECK FAIL`; the condition is traced here. (3) it marked Q1 Measured without describing the fallback `0x88e10018`; it is described here. (4) it placed `0x88e1450c` and `0x88e13f7a` "in" the 0x88e14630 loader; both lie in **earlier, separate functions**, corrected here. The main R-2 result stands: a recovery image whose first 8 bytes are not `ANDROID!` returns −1 before the write. The second pass adds the decisive point for W2: an **unsigned image with valid `ANDROID!` magic is written to recovery** (the signature failure does not block the Odin write).

## Input, integrity, method

`aboot.mbn`, private BL archive, measured on host: 788,104 bytes, SHA-256 `b85597465b90fc1868122981607dba4d79000e879561a2bd78ad73cc8a4071b2` (checked first; equals the task's value). Not in this repo.

**Load address (Measured), two ways that agree.** (1) 40-byte header, `image_dest_ptr` (0x0C) = **0x88e00000**; consistent (`image_dest_ptr+code_size 0xbd460 = signature_ptr 0x88ebd460`). (2) 10 of 10 A4 string virtual addresses occur as literal words. VA(fileoff F) = `0x88e00000 + F − 0x28`. **Disassembly:** `arm-none-eabi-objdump` (repo toolchain, no install) as ARM and Thumb; the entry at 0x88e00000 is an ARM vector table, the handlers are **Thumb-2** (decode as code in Thumb, nonsense in ARM). Labels: *Measured* (code shows it), *Inference* (basis named), *not established*.

## S1 — `0x88e0c048` is a coloured display print (Measured)

`0x88e0c048(color, fmt, …)` saves `r0` as a colour, runs `vsnprintf(buf,256,fmt,args)` (`0x88e1aa04`), then `bl 0x88e0bf00(color, buf, 1)`. `0x88e0bf00` is the framebuffer text renderer (character-cell geometry, screen width 960, framebuffer global `0x88ec1724`). So the argument is a **text colour**: `0xff0000` = red, `0xffff00` = yellow. It does **not** touch the warranty bit. The real warranty write is the separate call `0x88e0bb94` (→ `0x88e0b914`, an eMMC/command path, command `0xf7`); its exact target (RPMB / a partition / a fuse) is **not established** here.

## The Download/Odin write handler — recovery path (Measured)

Entry `~0x88e10420`. It fetches the partition entry (`0x88e07d78`), then dispatches by name. The **signed-partition name list** at 0x88e10756 is `sbl1, sbl2, sbl3, rpm, aboot, tz, boot, recovery, modem`. `"recovery"` matches (strncmp at 0x88e107c4) → 0x88e108c4 → (not "modem") → **0x88e107f8, the signature-verify region**. Order for recovery:

1. **Signature verify.** 0x88e107f8 prints `SECURE : Signature verification...`; it treats the **last 256 bytes** of the image as the signature (`r9 = size − 256`, `r8 = buf + r9`), hashes the rest (`0x88e0a374`→`0x88e0936c`), verifies (`0x88e0a378`→`0x88e084a0`) at 0x88e1081a. `0x88e1081e cmp r0,#0; bne 0x88e108fe`.
   - verify **ok** (`r0≠0`) → 0x88e108fe prints `SECURE : Signature verification succeed`, calls `0x88e0fa6c(name, 0)`, `b 0x88e10836`.
   - verify **fails** (`r0==0`, e.g. unsigned) → 0x88e10822 prints `SECURE : Signature verification failed`, calls `0x88e0fa6c(name, 1)`.
2. **`0x88e0fa6c(name, flag)` (Measured).** It keys on the name: `strncmp(name,"boot",4)` / `strncmp(name,"recovery",8)` (pools 0x88e0faf4/0x88e0faf8). For `recovery` it reads a stored flag (`0x88e07f5c`), sets bit 1 (`orr r6,r5,#2` at 0x88e0fab0), writes it back (`0x88e07f0c`) and **returns 0**. So at 0x88e10830 `cmp r0,#0; bne 0x88e1094a` the branch is **not** taken for recovery — `SECURE CHECK FAIL` is **not** reached. (Its message is `[Final]Secure check fail : %s`.)
3. **Magic check (Q1, Measured).** `0x88e105ae strcmp(name,"recovery")` → `memcmp(image, "ANDROID!", 8)` at 0x88e105c2 (length 8). If equal → accept (0x88e104d4). If not → fallback `0x88e10018`; if that also fails → `ODIN : image is not a boot image` (0x88e105d8), **return −1, no write**. (Boot is the mirror at 0x88e104b2/0x88e104c8.)
4. **0x88e104d4 → 0x88e10560, in order (Measured).** `bl`s: `0x88e1b27c` strcmp (0x88e104ee, a name flag), `0x88e0fc84` setup (0x88e104fc), `0x88e1b27c` strcmp (0x88e1052e), **`0x88e1327c` the write (0x88e10560)**. Conditionals: `0x88e104e6 bcc 0x88e10922` (**size** > partition → `ODIN : size too large`, return −6); `0x88e10504 beq 0x88e105e4`, `0x88e10514 beq 0x88e1073a`, `0x88e1053c bne 0x88e10602`, `0x88e10542 beq 0x88e1068e`, `0x88e10550 beq 0x88e106ac` (sub-handlers for sparse/fota modes). No signature call and no branch to 0x88e1094a in this range. After `0x88e1327c` returns 0 → `ODIN : partition '%s' updated` (0x88e1058a), return 0.

**Q2 — refusals, with conditions (Measured).** `ODIN : image is not a boot image` (−1): recovery/boot, when `memcmp(first 8,"ANDROID!")` ≠ 0 **and** fallback fails. `ODIN : size too large` (−6): any partition, when image sectors > partition sectors (0x88e104e6). `[Final]Secure check fail : %s` (0x88e1094a, −5): reached **only** from 0x88e10832 when `0x88e0fa6c(name,1)` ≠ 0 — which for `recovery`/`boot` is **not** the case (it returns 0). So **for recovery, the signature-verify failure does not refuse the image**; it prints "Signature verification failed", records a flag, and proceeds.

**Q3 — write only after checks (Measured).** The write is `bl 0x88e1327c` (0x88e10560); success prints `ODIN : partition '%s' updated`. The magic reject (−1) and the size reject (−6) return before 0x88e10560. A magic-refused image is not written. **But a valid-magic unsigned image reaches 0x88e10560 and is written** (recovery).

**Q4 — phone's reply (Measured in part).** The handler returns 0 (success) or a negative code (−1 magic, −5 secure-fail, −6 oversize, −4 write-fail) to its Odin caller. The exact USB bytes sent to the host are **not established** (the Odin response path was not traced). Host-side, a refusal shows as Heimdall's "Failed to confirm end of file transfer sequence!" (Heimdall source, not this firmware).

## S3 — the fallback `0x88e10018` (Measured)

It tests the image's **word[0] == 0xe1a00000** (0x88e10028 `cmn #0x1e600000`) **and word[0x20] == 0xea000002** (0x88e10036) — the bare ARM-kernel/zImage markers. payload.img (`ANDROID!…`, word[0x20] = tags 0x80200100) fails it; payload-invalid.img fails both this and the `ANDROID!` test → "image is not a boot image".

## S4 — the write routine and the cert magic (Measured)

The data is tested **before** the write call: signature at 0x88e0a378, image magic at 0x88e104c8/0x88e105be, and a **28-byte header magic** in the function at **0x88e1323c** — it copies 28 bytes and compares word[0] against **0xed26ff3a** (Qualcomm signed-image/cert magic); mismatch → `Invalid Magic Code! 0x%8x` (0x88e13262), return −1. `0x88e1323c` is called from the Odin path (e.g. 0x88e10694). `0x88e1327c` itself is the block write of the already-checked image; its internals were not traced (it is reached only after the checks above). Whether `0x88e1327c` re-checks after writing is **not established**.

## S5 — the start (boot)

- **(a) `0x88e0e2a4` (Measured).** On this build it is literally `movs r0,#1; bx lr` — returns the constant **1**. So at the loader 0x88e1463c `beq` is not taken and this build follows the **0x88e1463e branch**: `memcmp(image@0x88eff000, "ANDROID!", 8)` (0x88e14642/0x88e1464a); bad magic → `ERROR: Invalid boot image header` (0x88e1482a). Whether the other branch (0x88e146b2 → `0x88e04b84`) enforces a signature is **not established** (this build does not take it).
- **(b) The warranty-at-boot function (Measured; corrected placement).** `0x88e1450c` lies in a function at **~0x88e144xx**, *before* the 0x88e14630 loader. It is reached when a magic compare at 0x88e144c0 (word vs `0x574f4c44`) selects the custom/not-enforcing path. It prints `Set Warranty Bit : %s` in yellow (`0x88e0c048`, 0x88e1451e), then calls the real setter **`0x88e0bb94`** (0x88e14522) and `0x88e0bc28`, sets a flag, and **`b 0x88e14084` — it continues** (does not stop). So setting the warranty bit at boot is followed by continuing the boot, not a halt. Its exact entry/callers were not fully traced (**not established** beyond the above).
- **(c) `ERROR: Cannot read boot image signature`** is referenced at 0x88e13f7a and 0x88e147f6, in the signature-reading functions (`~0x88e13exx` and the 0x88e146b2 branch); on this build the boot gate (a) skips the 0x88e146b2 branch, so whether either prints here at boot is **not established**.

## S6 — SEANDROID / ENFORCING (Measured)

`SEANDROIDENFORCE` exists as a string (VA 0x88ebcbec), referenced via a literal pool at 0x88e0fe94 (function `~0x88e0fdc4`). The specific messages the reviewer recalled — `RECOVERY IS NOT SEANDROID ENFORCING` and `Set Warranty Bit : recovery` — **do not exist** in this build (searched case-insensitively; only `SEANDROIDENFORCE` and the format `Set Warranty Bit : %s` are present). **payload.img ends with the 16-byte `SEANDROIDENFORCE` trailer and no 256-byte signature.** The Odin recovery write treats the last 256 bytes as the signature, so payload.img's tail verifies as a **failed** signature → `SECURE : Signature verification failed` → `0x88e0fa6c(recovery,1)=0` → the image is still **written** (it is not refused for lacking a signature). What the boot path does with the trailer specifically is **not established** (the 0x88e0fdc4 user was not fully traced).

## S7 — payload.img against each test found

| Test (where) | What it checks | payload.img | Predicted result |
| --- | --- | --- | --- |
| Odin signature (0x88e0a378) | last 256 bytes as a signature over the rest | unsigned (16-byte `SEANDROIDENFORCE` trailer, no sig) | **fails verify, but not refused** — prints "Signature verification failed"; `0x88e0fa6c(recovery,1)=0` → proceeds (Measured) |
| Odin magic (0x88e105be) | first 8 bytes == `ANDROID!` | `ANDROID!` | **PASS** (W1's `INVALID!` failed here) (Measured) |
| Odin size (0x88e104e6) | image sectors ≤ partition sectors | 6,160 B vs RECOVERY 10,485,760 B | **PASS** (Measured) |
| Odin write (0x88e10560) | writes the buffered image | — | **WRITTEN** — payload.img is written to recovery (Measured, from the path above) |
| Odin warranty bit on this write | — | — | **not established** — `0x88e0bb94` was not seen on the recovery Odin-write path (it is on the boot path and the system/persist entry path) |
| Boot magic (0x88e1464a) | first 8 bytes == `ANDROID!` | `ANDROID!` | **PASS** (Measured) |
| Boot signature enforcement (0x88e146b2/0x88e04b84) | — | — | **cannot predict** — this build's gate `0x88e0e2a4`=1 skips that branch; its enforcement not established |
| Boot warranty bit (0x88e144xx) | custom/not-enforcing → set & continue | unsigned | **Inference:** likely set at boot, then boot continues (the function sets it and `b 0x88e14084`); exact trigger condition not established |

**What would have to be known** to close the two unpredictable rows: whether the Odin recovery write sets the warranty bit (trace `0x88e0bb94` reachability on that path), and what the boot path does for an unsigned-but-valid-magic recovery image given `0x88e0e2a4`=1 (trace the 0x88e1463e branch to the jump).

## Q7 — prediction vs Part B

Updated from the above. W1 wrote `payload-invalid.img` (`INVALID!`, unsigned) to recovery: signature verify fails → `SECURE : Signature verification failed`, then the magic check fails (`INVALID!` ≠ `ANDROID!`) and the fallback fails → `ODIN : image is not a boot image`, −1, **no write**. So the phone's Download screen most likely showed **`SECURE : Signature verification failed`** followed by **`ODIN : image is not a boot image`**, and no "partition updated". Whether the warranty bit changed at W1 is **not established** (the setter was not on this path, but this is not proof it was untouched). Part B transcriptions are not yet recorded, so this is not yet checked against them; any disagreement will be recorded here when Part B is in.

## Sources (exact addresses)

Odin: entry 0x88e10420; name list 0x88e10756 (`sbl1…modem`); recovery→verify 0x88e107c4/0x88e108c4/0x88e107f8; hash 0x88e0a374→0x88e0936c; verify 0x88e0a378→0x88e084a0 (0x88e1081a); succeed/fail 0x88e108fe/0x88e10822; `0x88e0fa6c` (names at 0x88e0faf4=`boot`,0x88e0faf8=`recovery`); SECURE CHECK FAIL 0x88e10832→0x88e1094a; magic 0x88e104c8(boot)/0x88e105be(recovery); fallback 0x88e10018 (0xe1a00000 / 0xea000002); size 0x88e104e6→0x88e10922; write 0x88e10560→0x88e1327c; success 0x88e1058a; cert magic 0x88e1323c (0xed26ff3a)→0x88e13262. Print: `0x88e0c048`→`0x88e1aa04`+`0x88e0bf00`; warranty setter `0x88e0bb94`→`0x88e0b914`. Boot: loader 0x88e14630; gate `0x88e0e2a4`(=1); boot magic 0x88e1464a→"Invalid boot image header" 0x88e1482a; warranty-at-boot ~0x88e144xx (print 0x88e1451e, set 0x88e14522, continue `b 0x88e14084`); "Cannot read boot image signature" 0x88e13f7a/0x88e147f6. Strings: `SECURE : Signature verification…/succeed/failed` 0x88e3affc/0x88e3b020/0x88e3b04c; `[Final]Secure check fail : %s` 0x88e3b390; `SEANDROIDENFORCE` 0x88ebcbec.

## Limits

Nothing touched the phone. No firmware and no disassembly listing is in this repo. Items marked "not established" were not followed to a definite answer and are not filled from any outside paper.
