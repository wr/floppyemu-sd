# femu-sd

Get disk images onto a [BMOW FloppyEmu](https://www.bigmessowires.com/floppy-emu/)
SD card without ever seeing **"file not contiguous"** again.

## The problem

FloppyEmu requires every disk image to occupy a contiguous run of sectors on
the SD card's FAT filesystem. That sounds like it should just happen — and on
a fresh card it does — but modern OSes sabotage it:

- macOS's FAT driver allocates **first-fit from the front of the card**, so
  once you've deleted and re-copied images a few times, free space is Swiss
  cheese and the next copy gets shredded into the holes.
- Spotlight, fseventsd, and AppleDouble `._*` files write to the card
  *during* your copy and split it — even on an otherwise clean card.

The result is the classic FloppyEmu experience: the image you copied
yesterday works, today's refuses, and renaming it sometimes "fixes" it
(that's luck, not the filename — the copy landed past the fragmentation).

We diagnosed this by parsing a misbehaving card's FAT directly; every image
the Emu refused really was fragmented, every one it accepted was contiguous.

## The tool

```
femu-sd image.dsk                copy an image to the card, the safe way
femu-sd push a.dsk b.po          several at once (push is the default verb)
femu-sd list                     what's on the card
femu-sd check                    read the FAT: which files are contiguous?
femu-sd repair                   repack a fragmented card (one-time fix)
femu-sd eject                    flush + eject
```

The card is auto-detected (it's the mounted FAT volume); pass a path like
`/Volumes/SDCARD` as the last argument if you have several.

What `push` does that `cp` doesn't:

- If a **same-size file already exists** on the card, it's overwritten
  **in place** (`dd conv=notrunc`) — the file keeps its clusters, so an
  image the Emu already loads can never become fragmented by an update.
  Raw floppy images are fixed-size, so this covers the everyday case.
- Fresh copies are made with Spotlight indexing disabled and the
  AppleDouble droppings cleaned up afterward.

`check` reads the FAT tables straight off the raw device (sudo, read-only,
FAT16 and FAT32) and tells you *before* the Emu does. `repair` is the
documented BMOW remedy — copy everything off, wipe, copy back in one pass —
automated, with the backup kept until you delete it.

## Install

It's one shell script and one Python file, no dependencies beyond python3
for `check`:

```sh
git clone https://github.com/wr/floppyemu-sd
cd floppyemu-sd && ln -s "$PWD/femu-sd" /usr/local/bin/femu-sd
```

macOS and Linux. (On Linux the metadata-noise problem mostly doesn't exist,
but first-fit fragmentation still does, and `check`/`repair`/`push` work the
same.)

## Not affiliated

Not affiliated with Big Mess o' Wires — just fans who lost an evening to a
fragmented card. The FloppyEmu manual (Appendix A) documents the contiguity
requirement and the manual repair procedure this tool automates.

MIT license.
