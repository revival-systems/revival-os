# Phase 2 image 2: the text console

**Status: built for the phone, tested only in QEMU, never written to the phone, and not approved for a write.** A write needs an amendment in the write plan's issue (#28) that names this image's commit, size and SHA-256 ([AGENTS.md](../../AGENTS.md), hardware safety contract, rule 1; [write-plan-draft.md](write-plan-draft.md), "Next images"). Nothing in this document is a hardware result.

The first image ([boot-payload-research.md](boot-payload-research.md), `boot/samsung-serranolte/payload.rs`) proved that our code runs on the GT-I9195. It showed nine numbers as rows of white and black cells, which had to be decoded from a photograph ([session record of 2026-11-18](../evidence/phase-2/2026-11-18-v5-session.md)).

This image shows text. It is the tool every later step needs: an image that can say in words what it found, on the phone's own screen, with no cable and no decoder.

It is **not** a shell and not a kernel. Nothing can be typed into it. It prints one report and then counts.

## Labels

| Label | Meaning |
| --- | --- |
| **Measured** | Read from the owner's phone in the session of 2026-11-18; the session record holds it. |
| **Source** | Stated in a cited file, or in published code. Not checked on the phone. |
| **Inference** | Our conclusion. No source states it. |
| **Unknown** | Not known for this phone. The entry says what resolves it. |
| **Emulator** | Seen in QEMU by `make test-console`. Not a hardware result. |

## The screen

White characters on black, 30 columns by 40 lines, the whole panel. Each character is a 5×7 glyph drawn three times its size in an 18×24 pixel cell. 30 × 18 = 540 and 40 × 24 = 960, so the grid covers the panel exactly, with no margin.

What the phone should show, as far as it can be known in advance. The first nine lines follow from the measured registers. The tag list below them is **made up** for this sample: what the bootloader really passes is what the image is for.

```text
REVIVAL OS
PHASE 2 IMAGE 2
SELFTEST 22BECBA4 OK
R0 00000000 R1 00000E8F
R2 80200100 R3 00000000
MACH 3727
CPSR 60000193 SVC I1 F0 A1 T0
SCTLR 00C5487A M0 C0 I0 A1 V0
ENTRY 80208000 OK
ATAGS 80200100
 CORE
 MEM 08000000 AT 80200000
 MEM 10000000 AT 90000000
 INITRD2 82200000 SZ 00000000
 REVISION 0000000B
 SERIAL HIDDEN
 TAG 4D534D70 W12
 CMDLINE console=<4>
  androidboot.hardware=<4>
  user_debug=<2>
  ...
 END 8 TAGS

(lines not used stay black)

MDP4 88100000 IS FB
TICK 00000007
```

`make console-sample` writes this sample as a picture, `build/boot-serrano-console/console-sample.png`.

| Line | Meaning |
| --- | --- |
| `SELFTEST 22BECBA4 OK` | The image summed its own eight-word table on the phone and got the expected value, the same one the first image showed. `BAD` with another value means the table was not loaded intact or the arithmetic went wrong. It checks those eight words, not the whole image. |
| `R0` to `R3` | The four registers as the bootloader left them. r3 was not shown by the first image (**Unknown** until this image runs). |
| `MACH 3727` | r1 in decimal: the machine number. |
| `CPSR … SVC I1 F0 A1 T0` | The processor state at entry: the mode by name, then one digit each for the IRQ mask, the FIQ mask, the abort mask and the Thumb bit. 1 means the bit is set. |
| `SCTLR … M0 C0 I0 A1 V0` | The system control register: MMU, data cache, instruction cache, alignment checking, high vectors. 1 means on. |
| `ENTRY 80208000 OK` | The address the image was entered at. The report is printed only if it is the address the image is linked for; see "If the image is loaded somewhere else". |
| `ATAGS 80200100` | r2 again, taken as the address of the bootloader's tag list, followed by one line for each tag. |
| `MDP4 88100000 IS FB` | The display controller's framebuffer-address register, and whether it names the buffer the image draws in. Before the register is read the line says `MDP4 READ PENDING`. |
| `TICK 00000007` | A counter that goes up by one after every 4,194,304 turns of a wait loop, for as long as the phone is on. A counter that moves shows the processor is still running our code. |

The last two lines are fixed. Whatever the report above them does, they are always the bottom two lines of the panel.

### The tag list

| Line | Meaning |
| --- | --- |
| ` CORE` | The list's first tag. ` CORE PAGE xxxxxxxx` if it carries a page size. |
| ` MEM size AT start` | One region of memory the bootloader reports. |
| ` INITRD2 start SZ size` | Where the bootloader put the boot image's ramdisk, and how long it is. |
| ` REVISION xxxxxxxx` | The board revision. |
| ` SERIAL HIDDEN` | A serial-number tag is present. Its words are never drawn. |
| ` CMDLINE …` | The kernel command line: for each word its name and the **length** of its value, `name=<length>`, or `<length>` alone for a word that has no `=`. |
| ` TAG kkkkkkkk Wn` | A tag of a kind this image does not know: its kind, and how many words follow its header. The words are never drawn. |
| ` END n TAGS` | The list ended properly after n tags. A second line ` END KIND xxxxxxxx` appears if the ending tag's kind word is not 0. |
| ` STOP SIZE xxxxxxxx` | A tag claims a size of 1 word, or of more than 2,048. The walk stops. |
| ` STOP PAST PAGE END` | A tag, or its header, would run past the end of the tag page. The walk stops. |
| ` STOP AT 64 TAGS` | 64 tags were shown and the list goes on. The walk stops. |
| `ATAGS xxxxxxxx OUT OF PAGE` | r2 is not inside the tag page. Nothing is read. |
| `ATAGS xxxxxxxx UNALIGNED` | r2 is not a multiple of 4. Nothing is read. |
| `ATAGS xxxxxxxx DEVICE TREE` | The first word is a device tree's magic number. It is not a tag list and is not walked. |

If the report needs more than its 38 lines, the rest is dropped and a `+` is drawn in the last cell of line 38. The console never scrolls: a photograph must show a still screen.

That the phone passes a tag list at all is an **Inference**: the first image measured r2 = 0x80200100 and the word there as 2, which is the size word of an empty `CORE` tag. The kind word next to it was not measured.

## What it never shows

A photograph of this screen is evidence, and evidence gets shared. The repository's rule 7 forbids serial numbers and other identifiers anywhere in it, in an issue, in a pull request or in a chat. A phone's bootloader passes exactly such values to the kernel. So the image is built so that it **cannot** draw them:

- **Command-line values.** `boot/samsung-serranolte/console/atags.rs` gives the rest of the image a word's name and the length of its value, never a byte of the value. A word with no `=` gives only its length. Double quotes are honoured as the Linux kernel honours them, so a quoted value with spaces in it stays one value.
- **The serial tag.** Only the fact that it is there.
- **Tags of unknown kinds.** Only the kind and the length.
- **A device tree.** Only the fact that it is one.

What is drawn: register values, addresses and sizes of memory regions, the board revision, and the names of command-line words. Names are the same on every phone of this model (**Inference**; if a name on this phone turns out to hold an identifier, the photograph is redacted like any other, and the rule is tightened).

## What it touches

| | What | Notes |
| --- | --- | --- |
| Writes | The framebuffer, 0x88100000 to 0x8827BB00 | Nothing else. Every write goes through one routine that clips to the panel. |
| Reads | The seven words `kstart.S` captured | On the image's own stack. |
| Reads | Its own code and constants | |
| Reads | The tag page, 0x80200000 to 0x80208000 | Only if r2 is inside it and a multiple of 4; only whole words; never past its end. |
| Reads | One register, 0x05190008 (MDP4 `DMA_P` buffer address) | Once, after the report is complete. **Measured:** the first image read it on the phone; it returned 0x88100000 and did not hang. Never written. |

It writes no peripheral register, uses no storage and does not reset the phone. Under rule 1's standing approval it is therefore a "further test image", not an image that "does something new to the hardware" (reviewer's reading; the amendment in the issue states it).

No heap, no allocator, no interrupts, no timer, no watchdog, no `svc`, no `core::fmt`, and no code path that can panic.

| Region | Range | Source |
| --- | --- | --- |
| Tag page | 0x80200000 to 0x80208000 | **Source:** boot-image parameters. **Measured:** r2 = 0x80200100. |
| Image and its 64 KiB stack | from 0x80208000; under 80 KiB in all, and `link.ld` allows at most 16 MiB (to 0x81208000) | `boot/samsung-serranolte/link.ld`. **Measured:** entry at 0x80208000. |
| Framebuffer | 0x88100000 to 0x8827BB00 (1,555,200 bytes) | **Measured:** the buffer the panel shows starts at 0x88100000. Its size follows from the panel geometry, which is **Source**. |

The three do not overlap.

## How it is built

| File | What it is |
| --- | --- |
| `boot/samsung-serranolte/kstart.S`, `link.ld` | **The first image's files, unchanged.** Everything that runs before Rust (the vectors, the register capture, the stack) is the code that has already run on the phone. |
| `console/main.rs` | The entry `payload_main`, the report, the counter. |
| `console/board.rs` | Every address and size the image uses, each with its evidence label. |
| `console/fb.rs` | The framebuffer and its one operation, a clipped rectangle fill. The only code that writes to the screen. |
| `console/console.rs` | Characters, lines, wrapping, hexadecimal and decimal numbers. |
| `console/atags.rs` | The tag-list walk and the command-line splitter. No `unsafe`, no addresses: it works on a slice of words. |
| `console/font.txt` | The glyphs, drawn for this project: 95 characters, ASCII 0x20 to 0x7E. The single source of the font. |
| `console/font.rs` | The table generated from `font.txt` by `tools/gen_console_font.py`. Committed; a build never runs the generator; a test fails if the two disagree. |

`make console` builds `build/boot-serrano-console/console.bin` (the kernel-slot bytes) and `console.img` (the Android boot image around them, packed by `tools/pack_bootimg.py` exactly as the first image is). The directory is separate from `build/boot-serrano/` on purpose: the write plan's host check lists the `.img` files there and must keep finding the first image only.

The first image is frozen and is not touched: its sources, its hashes and its tests are as they were.

## Design decisions

**Per-line clearing, no full-screen clear.** A line is painted black at the moment the text enters it. After the report, the lines it did not reach are cleared, then the two fixed lines. So the bootloader's picture is replaced from the top down, and if the image stops early the photograph shows how far it got.

**Byte writes.** Every framebuffer write is one volatile byte. Bytes need no alignment (see below) and make the order of the colour bytes irrelevant: a pixel's three bytes all get the same value, so only greys can be drawn and white is white in any order. **Measured:** the order is blue, green, red. This is the simple form, not the fast one. Drawing the full screen is about 2 million byte writes with the caches off; how long that takes on the phone is **Unknown** until the session.

**Alignment.** **Measured:** the bootloader enters the image with alignment checking on (SCTLR bit 1), so an unaligned word access would fault. The image reads words only from places it has checked or that the compiler aligns. The compiler itself is told never to generate an unaligned access: the Rust target `armv7a-none-eabi` has `+strict-align` among its built-in features (**Source:** rustc's target specification, `compiler/rustc_target/src/spec/targets/armv7a_none_eabi.rs`). The QEMU tests run the image with alignment checking on, after showing that the QEMU in use really faults an unaligned load.

**The order of risk.** Everything that only reads memory comes first. The one register read comes after the report is complete and after both fixed lines are in a known state, so a hang or fault there leaves the whole report on screen with `MDP4 READ PENDING` under it.

**Faults.** As in the first image, every exception vector is `kstart.S`'s halt. A fault draws nothing and stops; what was drawn stays. Saying which fault happened is Phase 3a's work.

**No panic.** The image contains no panic code at all, which a test checks in the linked file. Indexing is done with checked lookups and slice patterns, never with an index that could be out of range.

**If the image is loaded somewhere else.** The image is linked for 0x80208000 and reaches its text and its font through absolute addresses. If it were entered at another address those would point at memory that is not the image, and no text could be trusted. So the entry address is checked first. If it is wrong, the image draws 20 white and black stripes across the whole panel, which need no text and no table, and stops. **Measured:** the phone entered the first image at 0x80208000 in five of five trials, so stripes are not expected.

**The counter.** The wait between two steps is a counting loop, with volatile accesses so that the compiler keeps it. No timer and no `wfi`: with interrupts masked and nothing set up to raise one, a `wfi` would never return. How long one step takes on the phone is **Unknown**; the session's video gives it, and with it a first measure of how fast the processor runs our code with the caches off. `make console-sizes` prints the loop's instructions.

**No margin.** Text starts at the panel's first pixel. If the session shows the panel's edge is hard to photograph, the next image gives up a column and a line for a margin.

**Size.** The flat image may not exceed 8,192 bytes; a test fails if it does. `make console-sizes` prints its size at optimisation levels 2, s and z.

## Tests

`make test-console` (part of `make check`). Everything here is **Emulator** evidence or a build check. The host oracle is `tests/boot/console_v2.py`; the QEMU harness is `tests/boot/run_console.py`; the oracle's own unit tests are `tests/boot/test_console_v2.py` (run by `make test-unit`).

The oracle works out the expected screen from the description in this document and from `font.txt`. It does not share code with the image. The harness fills the framebuffer with a byte the image never writes before each run, so a dump that equals the oracle shows that the image wrote every byte of the panel.

| Test | What it can show |
| --- | --- |
| `console-font-generated` | `font.rs` is exactly what `font.txt` gives. |
| `console-size` | The flat image is within its limit. |
| `console-no-system-calls`, `console-symbols`, `console-elf-attributes` | As for the first image: no `svc`, nothing undefined, ARMv7-A soft-float. |
| `console-no-panic-code` | The linked image has no `core::panicking` and no `core::fmt` symbol. |
| `console-corrupt-image-rejected`, `console-image-unchanged` | A one-byte change is caught by the SHA-256. |
| `console-vector-header` | The image starts with `kstart.S`'s vectors and zImage words. |
| `qemu-console` | With no handoff, the screen is byte-exact, and byte-exact again after the counter has stepped. |
| `qemu-console-device-handoff` | Entered as the phone enters it, with a sample tag list and the register reading 0x88100000: byte-exact; none of the sample's hidden values can be read back from the screen; the tag page is unchanged. |
| `qemu-console-alignment-control` | This QEMU faults an unaligned word load when alignment checking is on. Without this, the next test would prove nothing. |
| `qemu-console-alignment-checked` | The same handoff with alignment checking on, as on the phone: byte-exact, no fault. |
| `qemu-console-tag-lists` | Twenty malformed and edge-case tag lists, one run each: byte-exact, no fault. They cover r2 outside the page and unaligned, the first and last word of the page, a device tree, sizes of 1 and 2,049, the largest tag, a tag that runs past the page end, 65 tags, an ending tag with a kind, a report longer than the screen, and the command-line forms (quotes, no `=`, empty name, empty value, a name longer than a line, bytes that are not printable, no terminating zero). |
| `qemu-console-noise` | Four tag pages of pseudo-random bytes: byte-exact, no fault, and the walk stays inside the page. |
| `qemu-console-moved` | Loaded and started at another address: the stripes, then a halt, no fault. |
| `qemu-console-fault-halts` | With memory that ends inside the framebuffer, the write past its end faults, the processor rests in the halt loop in abort mode, and everything drawn before is byte-exact. |
| `console-bootimg-valid` | An independent reader accepts every field of `console.img`. |
| `console-repro-identical` | Two clean builds give identical bytes. |

After every QEMU run the harness also checks that the tag page still holds exactly what was stored and that 64 KiB on each side of the framebuffer were not written.

What the emulator cannot show: the panel, its geometry, its colours, how long anything takes, what the bootloader passes, and whether the register read behaves again as it did. Those are what the session is for.

## What is not known

| Question | Label | What resolves it |
| --- | --- | --- |
| What r3 holds at entry | **Unknown** | This image's first line of registers. |
| What tags the bootloader passes, and what the command line's words are | **Unknown** | This image's report. |
| How much memory the bootloader reports, and where | **Unknown** | The ` MEM` lines. The top of usable memory in `docs/hardware/gt-i9195.md` is unverified. |
| Panel width, height and stride | **Source**; the first image's photographs are consistent with them | A screen of text that reads correctly edge to edge. |
| How long the screen takes to draw, and one counter step | **Unknown** | The session's video. |
| Whether the hardware watchdog resets the phone while the image counts | **Unknown** (the first image's videos were not read) | The session's video: whether the counter runs on, and for how long. |

## Not in this image

No input, no scrolling, no colours, no second page of output, no fault report, no timer, no interrupts. Each comes when a milestone needs it ([ROADMAP.md](../../ROADMAP.md)).
