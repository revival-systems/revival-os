# LANDFALL case study — relevance to Revival OS

**Status:** Original research notes based on inspection of the supplied Black Hat USA 2026 recording (selected visual slides) and corroborating Unit 42 / conference descriptions. No full audio transcription was available during this review.

## What the attack targeted

LANDFALL involved malformed **DNG (Digital Negative / TIFF-family)** image files exploiting **CVE-2025-21042** in Samsung's Android image-processing library. Unit 42 names the affected component as **libimagecodec.quram.so**. The research describes potential zero-click delivery, reportedly through messaging / image-handling flows, and a loader that leads to a surveillance implant.

The presentation illustrates an entry path from received WhatsApp media into Android media storage/scanning and Samsung's **com.samsung.ipservice**. Slides show a suspicious embedded shared object, **b.so**, targeting **AArch64**. These details describe the studied Android devices; they are **not proof of the vulnerability on the older, 32-bit Galaxy S4 Mini GT-I9195**.

**Layer classification:** untrusted content -> userspace/media or OEM image-processing code -> potential code execution / privilege crossing -> spyware. The research is **not primarily a Boot ROM, first-stage bootloader, or Secure Boot bypass**. Firmware and a correctly authenticated OS can still be vulnerable through post-boot software.

## What the uploaded presentation shows

1. **Discovery:** hunting malformed DNG samples submitted to public malware-analysis services rather than starting with a known spyware indicator. (Approx. 02:30–07:00)
2. **Embedded payload:** suspicious executable material and Android filesystem references hidden in image data; a compiled 64-bit ARM component. (Approx. 07:00–10:00)
3. **Likely trigger path:** the interaction between messaging media, Android's MediaStore, and Samsung's image-handling component. This is a *researcher-described path*, not a reproduced experiment here. (Approx. 10:00–13:00)
4. **Capabilities:** the talk lists microphone/call recording, location tracking, contacts, browser / SMS data, and collection of media. (Approx. 17:30)
5. **Infrastructure investigation:** configuration extraction, command-and-control grouping, Windows-malware signals and differential scanning. The slides discuss links to a state-aligned intrusion cluster; precise actor and vendor attribution should not be presented as certain solely from this talk. (Approx. 18:30–26:40)

## Why this matters to Revival OS

A bootloader checks *what OS starts*. LANDFALL illustrates what can go wrong *after* boot, when a service parses untrusted content automatically. Rust helps with memory safety but does not replace process isolation, access control, safe parser design, and careful exposure of privileged interfaces.

The experimental target of Revival OS is the Samsung **GT-I9195 (ARMv7 / 32-bit)**; slides about an **AArch64 Samsung Android payload** must not be mistaken for direct applicability to our hardware. We should study a **class of failures** rather than reproduce a phone-specific exploit.

## Defensive research backlog (no device writes authorized)

- **SR-LF-01 — Map parsing boundaries:** document every path through which CCTV snapshots, thumbnails, network images and imports reach a parser. Define trust levels and input ownership.
- **SR-LF-02 — Isolated parsing:** design a non-kernel media-decoding process with minimal permissions; reject parsing in privileged interrupt, driver or network service contexts.
- **SR-LF-03 — Malformed-input tests:** use harmless invalid DNG / TIFF test cases and fuzzing in host/QEMU environments to verify bounded reads/writes, arithmetic checks, timeouts and crash containment.
- **SR-LF-04 — Least privilege:** test that a compromised decoder cannot acquire microphone, camera, filesystem, network, credentials or kernel capabilities without authorization.
- **SR-LF-05 — Observable failures:** test structured parser-error reporting, process restarts and telemetry without exposing secret data.
- **SR-LF-06 — Independent evidence:** preserve a source link, SHA-256, speaker, timestamped claims and disclosure uncertainties in each case study.

### Suggested test acceptance criteria

In a host/QEMU prototype, a malformed image should cause at most a rejected input or contained decoder-process failure; it must not crash the kernel, corrupt adjacent memory, or grant a decoder unrelated I/O rights. Document test results before claiming an implemented defense.

## References

- Unit 42 primary report: https://unit42.paloaltonetworks.com/landfall-is-new-commercial-grade-android-spyware/
- Black Hat USA 2026 talk listing: https://blackhat.com/us-26/briefings/schedule/
- Virus Bulletin speaker abstract: https://www.virusbulletin.com/conference/vb2026/abstracts/hunting-landfall-overlooked-images-state-linked-mobile-spyware/

## Open questions

- Obtain and review a complete, timestamped local transcript of the uploaded presentation.
- Which Samsung image-decoder responsibilities are expected in the minimum Revival OS CCTV application?
- What is the smallest unprivileged parser interface usable without a general-purpose Android media stack?
- How will we measure that malformed media cannot cause a kernel fault?
