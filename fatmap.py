#!/usr/bin/env python3
"""fatmap - read a FAT16/FAT32 volume's allocation table directly and
report whether each file is CONTIGUOUS, which is what a BMOW FloppyEmu
requires of disk images ("file not contiguous" otherwise).

    sudo python3 fatmap.py /dev/rdisk4s1        (macOS raw device)
    sudo python3 fatmap.py /dev/sdb1            (Linux)

Read-only. Exit code 1 if any file is fragmented, 2 on errors.
"""
import struct
import sys

# File types FloppyEmu can load (from the FloppyEmu manual). Keep in sync
# with emu_kind() in femu-sd.
IMAGE_EXTS = {".dsk", ".do", ".po", ".nib", ".woz", ".2mg", ".hdv",  # Apple II
              ".img", ".image", ".moof",                             # Mac/Lisa floppy
              ".hda", ".iso", ".cdr", ".toast"}                      # Mac HD / CD-ROM
ARCHIVE_EXTS = {".sit", ".hqx", ".bin", ".cpt", ".txt"}  # auto-"boxed" (<1.4 MB)
NOT_ARCHIVES = {"favdisks.txt"}  # the Favorites menu config, not a disk


def emu_kind(name: str) -> str:
    """'image', 'archive', or '' for a file FloppyEmu won't load"""
    low = name.lower()
    base = low.rsplit("/", 1)[-1]
    ext = "." + base.rsplit(".", 1)[-1] if "." in base else ""
    if ext in IMAGE_EXTS:
        return "image"
    if ext in ARCHIVE_EXTS and base not in NOT_ARCHIVES:
        return "archive"
    return ""


def crack(dev: str) -> int:
    f = open(dev, "rb")
    bpb = f.read(512)
    bps = struct.unpack_from("<H", bpb, 11)[0]
    spc = bpb[13]
    reserved = struct.unpack_from("<H", bpb, 14)[0]
    nfats = bpb[16]
    maxroot = struct.unpack_from("<H", bpb, 17)[0]
    total16 = struct.unpack_from("<H", bpb, 19)[0]
    fatsz16 = struct.unpack_from("<H", bpb, 22)[0]
    total32 = struct.unpack_from("<I", bpb, 32)[0]
    if bps == 0 or spc == 0:
        print("not a FAT volume (is this the right device?)")
        return 2
    fatsz = fatsz16 or struct.unpack_from("<I", bpb, 36)[0]
    total = total16 or total32
    rootsectors = (maxroot * 32 + bps - 1) // bps
    data_first_sector = reserved + nfats * fatsz + rootsectors
    clusters = (total - data_first_sector) // spc
    if clusters < 4085:
        print("FAT12 volume - too small for fatmap (and unusual for a FloppyEmu card)")
        return 2
    fat32 = clusters >= 65525
    kind = "FAT32" if fat32 else "FAT16"
    cluster_bytes = spc * bps
    print(f"{kind}: {bps} B/sector, {spc} sectors/cluster, {clusters} clusters")

    f.seek(reserved * bps)
    fat = f.read(fatsz * bps)

    def next_clus(c: int) -> int:
        if fat32:
            return struct.unpack_from("<I", fat, c * 4)[0] & 0x0FFFFFFF
        return struct.unpack_from("<H", fat, c * 2)[0]

    END = 0x0FFFFFF8 if fat32 else 0xFFF8

    def chain(first: int):
        out, c = [], first
        while 2 <= c < END and len(out) <= clusters:  # bound = cycle guard
            out.append(c)
            c = next_clus(c)
        return out

    def runs(ch):
        if not ch:
            return []
        r = [[ch[0], ch[0]]]
        for c in ch[1:]:
            if c == r[-1][1] + 1:
                r[-1][1] = c
            else:
                r.append([c, c])
        return r

    def read_cluster(c: int) -> bytes:
        f.seek((data_first_sector + (c - 2) * spc) * bps)
        return f.read(cluster_bytes)

    def dir_entries(data: bytes):
        lfn = {}
        for i in range(0, len(data), 32):
            e = data[i:i + 32]
            if e[0] == 0x00:
                return
            if e[0] == 0xE5:
                lfn.clear()
                continue
            attr = e[11]
            if attr == 0x0F:  # long-filename fragment
                part = e[1:11] + e[14:26] + e[28:32]
                lfn[e[0] & 0x1F] = part.decode("utf-16-le", "replace")
                continue
            if attr & 0x08 or e[0] == 0x2E:  # volume label, or "." / ".."
                lfn.clear()
                continue
            base = e[0:8].decode("ascii", "replace").rstrip()
            ext = e[8:11].decode("ascii", "replace").rstrip()
            if e[12] & 0x08:  # NT/macOS flag: 8.3 basename is lowercase
                base = base.lower()
            if e[12] & 0x10:  # ... extension is lowercase
                ext = ext.lower()
            short = f"{base}.{ext}" if ext else base
            name = "".join(lfn[k] for k in sorted(lfn)) if lfn else short
            name = name.split("\x00")[0].rstrip("￿")
            lfn.clear()
            first = struct.unpack_from("<H", e, 26)[0]
            if fat32:
                first |= struct.unpack_from("<H", e, 20)[0] << 16
            size = struct.unpack_from("<I", e, 28)[0]
            yield name, first, size, bool(attr & 0x10)

    # the root directory: cluster chain on FAT32, fixed region on FAT16
    if fat32:
        root_clus = struct.unpack_from("<I", bpb, 44)[0]
        rootdata = b"".join(read_cluster(c) for c in chain(root_clus))
    else:
        f.seek((reserved + nfats * fatsz) * bps)
        rootdata = f.read(rootsectors * bps)

    def walk(data: bytes, prefix: str, depth: int = 0):
        """yield (path, first, size) for every file, recursing into subdirs"""
        for name, first, size, is_dir in dir_entries(data):
            if name.startswith((".", "_")):
                continue
            path = f"{prefix}{name}"
            if is_dir:
                if first and depth < 32:
                    sub = b"".join(read_cluster(c) for c in chain(first))
                    yield from walk(sub, path + "/", depth + 1)
                continue
            yield path, first, size

    frag = skipped = 0
    rows = []
    for name, first, size in sorted(walk(rootdata, "")):
        kind = emu_kind(name)
        if not kind:
            skipped += 1
            continue
        rr = runs(chain(first)) if first else []
        if len(rr) <= 1:
            rows.append(("CONTIGUOUS", name, size, ""))
        else:
            frag += 1
            why = ("FloppyEmu will refuse this" if kind == "image"
                   else "FloppyEmu may refuse this archive")
            rows.append(("FRAGMENTED", name, size,
                         f"{len(rr)} extents  <-- {why}"))
    # columns sized to the widest entry, 4 spaces apart (same as femu-sd list)
    pw = max((len(r[1]) for r in rows), default=0)
    sw = max((len(str(r[2])) for r in rows), default=0)
    gap = " " * 4
    for status, name, size, note in rows:
        line = f"  {status}{gap}{name:<{pw}}{gap}{size:>{sw}} bytes"
        print(f"{line}{gap}{note}" if note else line)
    if skipped:
        print(f"({skipped} other file(s) skipped - not a type FloppyEmu loads)")
    if frag:
        print(f"{frag} fragmented file(s). Fix: femu-sd repair")
        return 1
    print("all files contiguous - the FloppyEmu will be happy")
    return 0

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    try:
        sys.exit(crack(sys.argv[1]))
    except PermissionError:
        print("permission denied reading the device - run with sudo")
        sys.exit(2)
