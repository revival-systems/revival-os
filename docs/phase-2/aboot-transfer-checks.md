# What the stock bootloader (aboot) checks at transfer and at start

**Draft, for the reviewer.** Task R-2, P3. Host-only study; nothing touched the phone. No part of the firmware and no disassembly listing is in this file.

## Purpose

W1 showed that this bootloader can refuse an image at the transfer; write plan v4 assumed it would not. This note records, from the bootloader's own code, what it checks when Download/Odin mode writes a partition and what it checks when it starts a boot image, and whether `payload.img` passes each check.

## Input and integrity

`aboot.mbn`, from the private BL archive, measured on the host: 788,104 bytes, SHA-256 `b85597465b90fc1868122981607dba4d79000e879561a2bd78ad73cc8a4071b2` (checked first; equals the value named in the task). The firmware itself is not in this repository.

## Method

**Load address, found two ways that agree (Measured).**

1. The 40-byte header at the start of the file (ten little-endian `uint32`: `image_id`, `header_version`, `image_src`, **`image_dest_ptr`**, `image_size`, `code_size`, `signature_ptr`, `signature_size`, `cert_chain_ptr`, `cert_chain_size` — the Qualcomm/Little-Kernel `mbn`/boot header used by `lk` `aboot`). `image_dest_ptr` (offset 0x0C) = **0x88e00000**. The header is internally consistent: `image_dest_ptr + code_size` = 0x88e00000 + 0xbd460 = 0x88ebd460 = `signature_ptr`, and `signature_ptr + signature_size` = `cert_chain_ptr`.
2. From the code: for each of the ten A4 strings, the 32-bit little-endian value `load_address + file_offset − header_size(0x28)` occurs in the file as a literal word (a pointer in a literal pool). **10 of 10** string virtual addresses are present as literals, which fixes the load address at 0x88e00000. A string at file offset F is therefore at VA `0x88e00000 + F − 0x28`.

**Disassembly.** `arm-none-eabi-objdump` (the repo's installed toolchain) as ARM and as Thumb, with the VA base above. The entry at 0x88e00000 is an ARM branch-vector table; the Download/Odin and boot handlers decode cleanly as **Thumb-2** and as nonsense in ARM, so they are Thumb. Raw listings are kept in the private scratch directory only.

**Labels:** *Measured* = the code shows it at the cited address; *Inference* = reasoned, basis named; *not established* = not determined from the code.

**Deviation:** the task named `arm-none-eabi-objdump`; it is already present in the repo toolchain (`~/.local/share/revival-os/toolchains/arm-gnu-toolchain-…/bin`), so no package was installed.

## The Download/Odin write handler (Thumb, entry ~0x88e10480)

The handler receives the uploaded image into a RAM buffer (its pointer is the global read via literal 0x88e106dc) and dispatches by partition name.

**Q1 — what is tested before "ODIN : image is not a boot image" is printed, for which partitions (Measured).**
For a partition named **"boot"**: 0x88e104b2 `strcmp(name,"boot")`; if equal, 0x88e104c8–0x88e104cc do `memcmp(image, "ANDROID!", 8)` — the **first 8 bytes** of the received image against the literal `ANDROID!` (length 8 set at 0x88e104c6). For a partition named **"recovery"** (gating string at pool 0x88e10704 = VA 0x88e36a00 = `"recovery"`): 0x88e105ae `strcmp(name,"recovery")`; if equal, 0x88e105be–0x88e105c2 do the same `memcmp(image,"ANDROID!",8)`. On a mismatch a fallback routine 0x88e10018 is tried (0x88e105ce); only if it also fails does the handler load "ODIN : image is not a boot image" (VA 0x88e3b3b0, at 0x88e105d8), print it (0x88e1a504), set the return to −1 (0x88e105de) and return. **So the test is `memcmp(first 8 bytes, "ANDROID!")`, made for the `boot` and `recovery` partitions; the string prints only when the magic does not match and the fallback also fails.**

**Q2 — other refusals between transfer-end and the write (Measured, with one limit).**
- **Size:** 0x88e104dc–0x88e104e6 compares the image size against the partition size; if too large it prints "ODIN : size too large" (0x88e10922) and returns −6. Applies to any partition that reaches this stage, RECOVERY included.
- **Secure check (signature):** the "SECURE CHECK FAIL : %s" path at 0x88e1094a sets the Knox warranty bit (call 0x88e0c048 with 0xff0000) and returns −5 — the signature check of a locked bootloader. **Whether it is enforced for a RECOVERY write on this build is not established** (it depends on the write/verify routine 0x88e1327c and the lock state, not fully traced here).
- A write failure returns −4 (0x88e1092e).

**Q3 — is flash written only after the tests pass? Can a refused image have changed RECOVERY? (Measured.)**
The write is the call to 0x88e1327c at 0x88e10560; the success line "ODIN : partition '%s' updated" (VA 0x88e3b44c) prints only after it returns 0 (0x88e10560 → 0x88e1058a). The magic test (0x88e104c8 / 0x88e105be) runs **before** the size test (0x88e104dc) and the write (0x88e10560), and its reject path returns −1 **without** reaching 0x88e10560. **A magic-refused image is therefore not written and cannot have changed RECOVERY.** (Download mode still cannot read the partition back; this is an argument from the write path, not a read-back.)

**Q4 — what the phone returns on refusal and on success (Measured in part; USB bytes not established).**
The handler returns 0 on success and a negative status on refusal (−1 bad magic, −5 secure-check fail, −6 oversize, −4 write fail) to its Odin caller. The exact bytes the phone then sends to the host over USB were **not established** (the Odin/USB response path was not traced). On the host side a refusal appears as no valid end-of-transfer acknowledgement — Heimdall's "Failed to confirm end of file transfer sequence!" (known from Heimdall's source, not from this firmware).

## The start (boot) path (Thumb, loader ~0x88e14630)

**Q5 — checks on the RECOVERY image before the jump, and the warranty bit (Measured, with limits).**
The loader reads the image to 0x88eff000, then: a gate 0x88e0e2a4 (0x88e14636) selects a verify path; on one branch it does `memcmp(image,"ANDROID!",8)` (0x88e14642–0x88e1464a) and, if the magic is wrong, prints "ERROR: Invalid boot image header" (via 0x88e1482a, VA 0x88e3c254) and fails. A **page-size** check prints "ERROR: Invalid boot image pagesize" (0x88e14786, VA 0x88e3c82c). A **signature** path (0x88e04b84 at 0x88e146b2) relates to "ERROR: Cannot read boot image signature" (0x88e13f7a, 0x88e147f6) and the secure check; "Invalid Magic Code! 0x%8x" (VA 0x88e3bf38) is referenced by a related routine at 0x88e13262. **"Set Warranty Bit : %s"** (VA 0x88e3b378) is referenced in this path at 0x88e1450c — a non-Samsung-signed image loaded here sets the warranty bit; **whether the start then continues or halts after setting it is not established** here. The jump to the kernel is the call at 0x88e146a2 (0x88e1392c), reached only after the magic (and, on the secure branch, the signature) checks.

## Q6 — payload.img against each test

| Test (where) | payload.img | payload-invalid.img (W1) | stock recovery.img | Predicted for payload.img |
| --- | --- | --- | --- | --- |
| Odin magic: first 8 bytes == `ANDROID!` (0x88e104c8 / 0x88e105be) | `ANDROID!` (Measured) | `INVALID!` (Measured) | `ANDROID!` (Measured) | **PASS** |
| Odin size ≤ partition (0x88e104dc) | 6,160 B (Measured) | 6,160 B | 8,935,696 B | **PASS** (RECOVERY = 10,485,760 B) |
| Boot page-size (0x88e14786) | 2048 (Measured) | 2048 | 2048 (Measured) | **PASS** (matches stock) |
| Signature / secure check (0x88e1094a Odin; 0x88e04b84 boot) | unsigned, Revival OS build | unsigned | Samsung-signed (sha `0e30955962…`) | **CANNOT PREDICT** — enforcement for a RECOVERY write/boot on this locked build not established |

Shared header fields (Measured): both images use `kernel_addr` 0x80208000, `tags_addr` 0x80200100, `page_size` 2048. payload.img: magic `ANDROID!`, kernel 1,636 B, total 6,160 B. The only field that made W1 fail is the 8-byte magic (`INVALID!` vs `ANDROID!`).

## Q7 — what the study predicts W1 showed, vs the read-only checks

**Prediction (from the code).** W1 wrote `payload-invalid.img` (magic `INVALID!`) to `recovery`. The magic test `memcmp(first 8, "ANDROID!")` fails and the fallback fails, so the handler prints "ODIN : image is not a boot image", returns −1 and does **not** write. Because the magic test runs **before** the secure/signature check, the warranty-bit step is not reached, so `KNOX WARRANTY VOID` should still read `0x0` after W1 and the Download screen should show a failed/aborted write, not a success.

**Agreement with Part B:** the owner's transcriptions of the W1 screens are **not yet recorded** (Part B is pending), so this prediction is not yet checked against them. To be completed when Part B is in; any disagreement will be stated here.

## Sources (exact addresses)

- **Load address:** header offset 0x0C (`image_dest_ptr` = 0x88e00000); consistency `0x88e00000 + 0xbd460 = 0x88ebd460`; 10 of 10 A4 string VAs present as literals.
- **Odin handler:** 0x88e10480 (entry); 0x88e104b2, 0x88e104c8, 0x88e104cc, 0x88e104d2 (boot magic); 0x88e105ae, 0x88e105be, 0x88e105c2, 0x88e105c8, 0x88e105d8 (recovery magic + reject); 0x88e10018 (fallback); 0x88e104dc, 0x88e10922 (size); 0x88e1094a (secure-check fail); 0x88e10560, 0x88e1327c (write); 0x88e1058a (success). Helpers: `memcmp` 0x88e1b204, `strcmp` 0x88e1b27c, print 0x88e1a504.
- **Boot loader:** 0x88e14630 (entry); 0x88e14636/0x88e0e2a4 (gate); 0x88e14642/0x88e1464a (boot magic); 0x88e1482a (invalid header); 0x88e14786 (pagesize); 0x88e146b2/0x88e04b84, 0x88e13f7a, 0x88e147f6 (signature); 0x88e13262 (invalid magic code); 0x88e1450c (Set Warranty Bit); 0x88e146a2/0x88e1392c (jump).
- **String virtual addresses:** `ANDROID!` 0x88e3b288; `ODIN : image is not a boot image` 0x88e3b3b0; `ODIN : size too large` 0x88e3b3d4; `ODIN : partition '%s' updated` 0x88e3b44c; `SECURE CHECK FAIL : %s` 0x88e3b314; `Set Warranty Bit : %s` 0x88e3b378; `Invalid Magic Code! 0x%8x` 0x88e3bf38; `ERROR: Invalid boot image header` 0x88e3c254; `ERROR: Invalid boot image pagesize` 0x88e3c82c; `ERROR: Cannot read boot image signature` 0x88e3c32c.

## Limits

Nothing here touched the phone. No firmware and no disassembly listing is in this repository. Where the code could not be followed to a definite answer — the secure-check enforcement for a RECOVERY write, the continue/halt after the warranty bit, the Odin USB response bytes — this note says "not established" rather than guessing, and does not fill the gap from any outside paper.
