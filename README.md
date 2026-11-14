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
femu-sd image.dsk Games/Mac      into a folder on the card (created if needed)
femu-sd image.dsk Mac/Lode.dsk   to a specific path and name on the card
femu-sd list                     what FloppyEmu can load, folders included
femu-sd check                    read the FAT: which files are contiguous?
femu-sd repair                   repack a fragmented card (one-time fix)
femu-sd eject                    flush + eject
```

The card is auto-detected (it's the mounted FAT volume); pass its mount
point, like `/Volumes/SDCARD`, as the last argument if you have several.

The optional destination after the image(s) is a path on the card, relative
to its root (the root if omitted). It's treated as a **folder** if it ends
in `/`, already exists as a folder on the card, or its last part has no
extension; otherwise it's the **full path and filename** to use (one image
only). The last argument is only taken as the destination if it isn't an
existing local file, and each install prints `source -> destination` so a
typo can't slip by silently.

What `push` does that `cp` doesn't:

- If a **same-size file already exists** on the card, it's overwritten
  **in place** (`dd conv=notrunc`) — the file keeps its clusters, so an
  image the Emu already loads can never become fragmented by an update.
  Raw floppy images are fixed-size, so this covers the everyday case.
- Fresh copies are made with Spotlight indexing disabled and the
  AppleDouble droppings cleaned up once the whole batch is done (deleting
  them between copies leaves holes the next copy would fragment into).

`check` reads the FAT tables straight off the raw device (sudo, read-only,
FAT16 and FAT32), walks every folder, and tells you *before* the Emu does.

`repair` is the documented BMOW remedy, automated: copy everything off,
**reformat the card**, copy everything back in one pass. Deleting the files
isn't enough. Directory clusters the root folder grew into, and macOS's
Spotlight/fseventsd files, survive a delete-all and split images copied back
around them. Reformatting is the only clean slate. Safety rails:

- It only reformats the device behind the card's own mount point, and only
  if it is removable media, FAT16/FAT32, and not part of the boot disk.
  The volume name and FAT type are kept.
- Before asking to continue, it shows the device's name, size, and how it's
  connected, and says whether it's confirmed to be an SD card. That's only
  possible in an SD slot macOS reports as "Secure Digital" (like a Mac's
  built-in reader). A USB card reader looks the same to macOS as a flash
  drive or external disk, so it says so.
- It refuses to start if the card is read-only (e.g. the lock switch is on)
  or there isn't room for the backup.
- The backup is checked file-by-file against the card before anything is
  erased, and the card is checked against the backup afterwards. The backup
  is kept until you delete it, and if anything fails, it tells you how to
  restore from it.

## File types

`list` and `check` cover every file type the FloppyEmu manual lists:

- **Disk images:** `.dsk .do .po .nib .woz .2mg .hdv` (Apple II),
  `.img .image .moof` (Mac/Lisa floppy), `.hda .iso .cdr .toast`
  (Mac hard disk / CD-ROM).
- **Archives:** `.sit .hqx .bin .cpt .txt`. The Emu wraps these in a
  temporary "box" floppy on the fly, but only if they are under 1.4 MB;
  `list` flags the ones that are too big. (`favdisks.txt`, the Favorites
  menu config, is not treated as an archive.)

`check` skips other files, since their layout doesn't matter to the Emu.
`push` will copy anything, with a note if it isn't a type the Emu loads.

## Install

It's one shell script and one Python file, no dependencies beyond python3
for `check`:

```sh
git clone https://github.com/wr/floppyemu-sd
cd floppyemu-sd && ln -s "$PWD/femu-sd" /usr/local/bin/femu-sd
```

macOS and Linux. (On Linux the metadata-noise problem mostly doesn't exist,
but first-fit fragmentation still does. `check` and `push` work the same;
`repair` on Linux deletes and re-copies the files rather than reformatting,
so it can't clear the leftovers described above.)

## Not affiliated

Not affiliated with Big Mess o' Wires — just fans who lost an evening to a
fragmented card. The FloppyEmu manual (Appendix A) documents the contiguity
requirement and the manual repair procedure this tool automates.

MIT license.
