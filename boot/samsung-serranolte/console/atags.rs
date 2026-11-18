//! atags.rs - read a bootloader tag list (ATAGS) without trusting it.
//!
//! Pure code: it takes a slice of words and touches nothing else, so it has no
//! `unsafe`, no address and no hardware in it. The caller decides which memory
//! the slice covers; this module never reads past the slice.
//!
//! A tag list is a run of tags. Each tag starts with two words: its size in
//! words (the two header words included) and its kind. A tag of size 0 ends
//! the list. `Walk` gives the tags one at a time and stops, saying why, at the
//! first thing that is not a well-formed tag.
//!
//! The command-line tag holds text. `Cmdline` splits it into words the way the
//! Linux kernel does and gives, for a `NAME=VALUE` word, the name and the
//! LENGTH of the value. It never gives a byte of a value, and never a byte of
//! a word that has no `=`. Values on a phone hold its serial number and other
//! identifiers; code that cannot obtain them cannot draw them.

/// Tag kinds this image knows by name.
pub const ATAG_CORE: u32 = 0x5441_0001;
pub const ATAG_MEM: u32 = 0x5441_0002;
pub const ATAG_INITRD2: u32 = 0x5442_0005;
pub const ATAG_SERIAL: u32 = 0x5441_0006;
pub const ATAG_REVISION: u32 = 0x5441_0007;
pub const ATAG_CMDLINE: u32 = 0x5441_0009;

/// What the first word reads as when the bootloader passed a device tree
/// instead of a tag list: the tree's magic number 0xD00DFEED is stored most
/// significant byte first.
pub const DEVICE_TREE_MAGIC: u32 = 0xEDFE_0DD0;

/// The walk gives at most this many tags.
pub const MAX_TAGS: usize = 64;
/// The largest tag the walk accepts, in words, header included.
const MAX_TAG_WORDS: u32 = 2048;

/// One step of a walk.
pub enum Step<'a> {
    /// A well-formed tag: its kind, and its words after the two header words.
    Tag { id: u32, body: &'a [u32] },
    /// The tag of size 0 that ends a list, and its kind word. In a correct
    /// list the kind is 0; any other kind is a malformed end.
    End { id: u32 },
    /// A size word that is 1, or more than `MAX_TAG_WORDS`.
    BadSize(u32),
    /// The tag, or its header, would run past the end of the slice.
    PastEnd,
    /// `MAX_TAGS` tags were given and the list goes on.
    TooMany,
}

/// Walks a tag list. After any step that is not a `Tag` it gives nothing more.
pub struct Walk<'a> {
    rest: &'a [u32],
    seen: usize,
    done: bool,
}

impl<'a> Walk<'a> {
    /// A walk over the list that starts at the first word of `words`.
    pub fn new(words: &'a [u32]) -> Self {
        Walk { rest: words, seen: 0, done: false }
    }

    /// How many tags the walk has given so far.
    pub fn seen(&self) -> usize {
        self.seen
    }

    fn step(&mut self) -> Step<'a> {
        let rest: &'a [u32] = self.rest;
        let (size, id) = match rest {
            [size, id, ..] => (*size, *id),
            _ => return Step::PastEnd,
        };
        if size == 0 {
            return Step::End { id };
        }
        if size < 2 || size > MAX_TAG_WORDS {
            return Step::BadSize(size);
        }
        if self.seen >= MAX_TAGS {
            return Step::TooMany;
        }
        let words = size as usize;
        match (rest.get(2..words), rest.get(words..)) {
            (Some(body), Some(after)) => {
                self.rest = after;
                self.seen += 1;
                Step::Tag { id, body }
            }
            _ => Step::PastEnd,
        }
    }
}

impl<'a> Iterator for Walk<'a> {
    type Item = Step<'a>;

    fn next(&mut self) -> Option<Step<'a>> {
        if self.done {
            return None;
        }
        let step = self.step();
        if !matches!(step, Step::Tag { .. }) {
            self.done = true;
        }
        Some(step)
    }
}

/// One piece of a command line, in order.
pub enum Piece {
    /// The next character of the name of a `NAME=VALUE` word.
    Name(u8),
    /// The name is complete; its value is this many bytes long.
    Value(u32),
    /// A word with no `=` in it, this many bytes long.
    Bare(u32),
}

/// Splits the text in a command-line tag's body into `Piece`s.
///
/// The text ends at its first zero byte, or at the end of the body. Words are
/// separated by white space, except inside double quotes, and a word's name
/// ends at its first `=`: the rules of the Linux kernel's `next_arg`.
#[derive(Clone, Copy)]
pub struct Cmdline<'a> {
    body: &'a [u32],
    /// Index of the next byte to look at.
    pos: usize,
    /// While `pos < name_end`, the bytes at `pos` are a name still to give.
    name_end: usize,
    /// While `pos < word_end`, a `NAME=VALUE` word is being given.
    word_end: usize,
}

impl<'a> Cmdline<'a> {
    /// The command line held in `body`, the words of a tag after its header.
    pub fn new(body: &'a [u32]) -> Self {
        Cmdline { body, pos: 0, name_end: 0, word_end: 0 }
    }

    /// Whether the text's terminating zero byte is inside the body. A command
    /// line without one is malformed: its text was cut off at the tag's end.
    pub fn is_terminated(&self) -> bool {
        self.body.iter().any(|word| word.to_le_bytes().contains(&0))
    }

    /// Byte `index` of the text; 0 past the end of the body. Words are little
    /// endian: byte 0 of a word is its least significant.
    fn byte(&self, index: usize) -> u8 {
        match self.body.get(index / 4) {
            Some(&word) => (word >> (8 * (index % 4))) as u8,
            None => 0,
        }
    }
}

impl<'a> Iterator for Cmdline<'a> {
    type Item = Piece;

    fn next(&mut self) -> Option<Piece> {
        if self.pos < self.name_end {
            let c = self.byte(self.pos);
            self.pos += 1;
            return Some(Piece::Name(c));
        }
        if self.pos < self.word_end {
            // `pos` is at the `=`; the value is everything after it.
            let length = self.word_end - self.pos - 1;
            self.pos = self.word_end;
            return Some(Piece::Value(length as u32));
        }

        while is_space(self.byte(self.pos)) {
            self.pos += 1;
        }
        let start = self.pos;
        let mut end = start;
        let mut equals: Option<usize> = None;
        let mut quoted = false;
        loop {
            let c = self.byte(end);
            if c == 0 || (is_space(c) && !quoted) {
                break;
            }
            if c == b'=' && equals.is_none() {
                equals = Some(end);
            }
            if c == b'"' {
                quoted = !quoted;
            }
            end += 1;
        }
        if end == start {
            return None;
        }
        match equals {
            Some(at) => {
                self.name_end = at;
                self.word_end = end;
                if start < at {
                    self.pos = start + 1;
                    Some(Piece::Name(self.byte(start)))
                } else {
                    // The word starts with `=`: an empty name.
                    self.pos = end;
                    Some(Piece::Value((end - at - 1) as u32))
                }
            }
            None => {
                self.pos = end;
                Some(Piece::Bare((end - start) as u32))
            }
        }
    }
}

/// White space as the C library's `isspace` has it: space, tab, line feed,
/// vertical tab, form feed, carriage return.
fn is_space(c: u8) -> bool {
    c == b' ' || (c >= 9 && c <= 13)
}
