//! board.rs - the GT-I9195 facts the console image relies on.
//!
//! Every address and size the image uses is here and nowhere else, each with
//! where it comes from. "Measured" means read from the owner's phone in the
//! session of 2026-11-18 (docs/evidence/phase-2/2026-11-18-v5-session.md);
//! "Source" means taken from published code or a document and not yet checked
//! on the phone beyond what that record says.

/// Start of the framebuffer the panel shows. Measured: the first image's rows
/// were visible in the buffer at this address in five of five trials, and the
/// display controller's register (below) held this value.
pub const FB_BASE: usize = 0x8810_0000;

/// Panel width and height in pixels, and bytes per pixel. Source (the mainline
/// fork's device tree; docs/hardware/gt-i9195.md). The first image drew with
/// these values and its rows photographed where they were expected, which is
/// consistent with them but is not a measurement of the panel.
pub const FB_WIDTH: usize = 540;
pub const FB_HEIGHT: usize = 960;
pub const FB_BYTES_PER_PIXEL: usize = 3;

/// Bytes from one pixel row to the next. Source, as above: no padding.
pub const FB_STRIDE: usize = 1620;

const _: () = assert!(FB_STRIDE == FB_WIDTH * FB_BYTES_PER_PIXEL);

/// The page the bootloader puts its tag list in, as a half-open range. Source
/// (boot-image parameters, docs/phase-2/boot-payload-research.md). Measured:
/// r2 was 0x80200100, inside it. The image reads tags only inside this range.
pub const TAGS_PAGE_LO: u32 = 0x8020_0000;
pub const TAGS_PAGE_HI: u32 = 0x8020_8000;

/// MDP4 DMA_P source-buffer address register. Source (docs/phase-2/
/// boot-payload-research.md section 3). Measured: reading it on the phone gave
/// 0x88100000 and did not hang. The image reads it once and never writes it.
pub const MDP_DMA_P_BUF_ADDR: usize = 0x0519_0008;

/// The address the image is linked to run at (link.ld). Measured: the
/// bootloader entered the first image at exactly this address.
pub const LINK_ENTRY: u32 = 0x8020_8000;
