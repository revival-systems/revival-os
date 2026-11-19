# Licences of third-party material

Revival OS's own code and documents are the project's. This directory holds the licence texts of material from others that the repository contains in some form.

## Fonts in the boot screen's stored pictures

The Phase 2 boot screen image ([screen-payload.md](../phase-2/screen-payload.md)) shows letters. Those letters are stored as small pictures in `boot/samsung-serranolte/screen/assets.bin`, which `tools/gen_boot_screen.py` drew from three font families on the build machine. **The repository does not contain the font files**, only pictures of some of their letters at one size, and the screen's titles as part of its background picture.

| Font | Version | Used for | Licence |
| --- | --- | --- | --- |
| DejaVu Sans Mono (regular, bold) | 2.37 | The command line, and the two lines at the top right | [DejaVu-Fonts-License.txt](DejaVu-Fonts-License.txt): the Bitstream Vera licence; DejaVu's own changes are in the public domain |
| DejaVu Sans Condensed (bold) | 2.37 | Values, labels, chips, the counter | The same file; it also holds the Arev licence, which covers glyphs this family took from Arev |
| Poppins (bold) | 4.004 | `REVIVAL OS`, the panel titles, `TICK` | [Poppins-OFL-1.1.txt](Poppins-OFL-1.1.txt): the SIL Open Font License 1.1 |

`DejaVu-Fonts-License.txt` is the licence text carried inside `DejaVuSansCondensed-Bold.ttf` itself (its licence field), unchanged. `Poppins-OFL-1.1.txt` is the copyright line carried inside `Poppins-Bold.ttf`, followed by the licence's standard text.

The reviewer's reading is that both licences allow this use. The reviewer is not a lawyer; this file records what was used and under which terms, so that anyone can check.

## The Revival OS mark and the icons

`boot/samsung-serranolte/screen/art.png` holds the Revival OS mark and nine icons. They were cut from the design picture for the boot screen that the owner supplied on 2026-11-19. No licence text for them is kept here.
