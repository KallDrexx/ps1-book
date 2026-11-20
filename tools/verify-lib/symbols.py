"""symbols.py -- symbol tables and PSX-EXE inspection for the verification harness.

Standard library only.

    syms = Symbols.from_sym("main.sym")          # armips -sym / -sym2 output
    syms = Symbols.from_elf("game.elf")          # mipsel-none-elf-nm
    syms = Symbols.load(path)                    # picks by extension/content
    syms["done"]            -> 0x800100A4        (KeyError with a helpful message)
    "done" in syms
    syms.get("results")     -> address or None
    syms.size("results")    -> bytes (sym2 / nm -S only) or None
    exe = PsxExe.load("main.ps-exe")
    exe.pc, exe.load_addr, exe.text_size, exe.code   (bytes of text segment)
    exe.disassemble()       -> [Insn(addr, word, text)]  via mipsel-none-elf-objdump
"""
import os
import re
import struct
import subprocess
from collections import namedtuple


class Symbols:
    def __init__(self, table=None, sizes=None):
        self.table = dict(table or {})
        self.sizes = dict(sizes or {})

    # ---- loading -------------------------------------------------------
    @classmethod
    def from_sym(cls, path):
        """Parse armips no$psx (.sym) or sym2 (`name,size`) files.

        Lines look like `80010000 main` or `800100AC results,00000008`.
        Compiler-generated data labels (`.dbl:0004`, `.byt:0008`, ...) and the
        leading `00000000 0` line are skipped.
        """
        table, sizes = {}, {}
        with open(path, "r", errors="replace") as f:
            for line in f:
                parts = line.strip().split(None, 1)
                if len(parts) != 2:
                    continue
                try:
                    addr = int(parts[0], 16)
                except ValueError:
                    continue
                name = parts[1].strip()
                size = None
                if "," in name:
                    name, _, sz = name.partition(",")
                    try:
                        size = int(sz, 16)
                    except ValueError:
                        pass
                if not name or name.startswith(".") or name == "0":
                    continue
                table[name] = addr
                if size is not None:
                    sizes[name] = size
        return cls(table, sizes)

    @classmethod
    def from_elf(cls, path, nm="mipsel-none-elf-nm"):
        """Symbols of an ELF via `nm -S`. (MIPS nm prints sign-extended 64-bit
        addresses like ffffffff80010108; we mask to 32 bits.)"""
        out = subprocess.run([nm, "-S", "--defined-only", path], capture_output=True,
                             text=True, check=True).stdout
        table, sizes = {}, {}
        for line in out.splitlines():
            p = line.split()
            if len(p) == 4:      # addr size type name
                table[p[3]] = int(p[0], 16) & 0xFFFFFFFF
                sizes[p[3]] = int(p[1], 16)
            elif len(p) == 3:    # addr type name
                table[p[2]] = int(p[0], 16) & 0xFFFFFFFF
        return cls(table, sizes)

    @classmethod
    def load(cls, path):
        if path.endswith((".elf", ".o", ".a")) or _is_elf(path):
            return cls.from_elf(path)
        return cls.from_sym(path)

    # ---- access --------------------------------------------------------
    def __contains__(self, name):
        return name in self.table

    def __getitem__(self, name):
        try:
            return self.table[name]
        except KeyError:
            close = [n for n in self.table if n.lower() == name.lower()]
            hint = f" (did you mean {close[0]!r}?)" if close else ""
            raise KeyError(f"symbol {name!r} not found in program{hint}") from None

    def get(self, name, default=None):
        return self.table.get(name, default)

    def size(self, name):
        return self.sizes.get(name)

    def names(self):
        return sorted(self.table, key=self.table.get)

    def require(self, *names):
        """Return the list of names that are missing (empty list == all present)."""
        return [n for n in names if n not in self.table]

    def resolve(self, ref):
        """Accept a symbol name, `name+off`, or an int address."""
        if isinstance(ref, int):
            return ref
        m = re.fullmatch(r"([A-Za-z_.$][\w.$]*)\s*([+-]\s*(?:0x[0-9a-fA-F]+|\d+))?", ref.strip())
        if not m:
            raise ValueError(f"bad symbol reference {ref!r}")
        off = int(m.group(2).replace(" ", ""), 0) if m.group(2) else 0
        return self[m.group(1)] + off

    def symbol_at(self, addr):
        """Name of the closest symbol at or before addr (for messages)."""
        best = None
        for n, a in self.table.items():
            if a <= addr and (best is None or a > self.table[best]):
                best = n
        return best


def _is_elf(path):
    try:
        with open(path, "rb") as f:
            return f.read(4) == b"\x7fELF"
    except OSError:
        return False


Insn = namedtuple("Insn", "addr word text")


class PsxExe:
    """Parsed PSX-EXE (header is 0x800 bytes, fields little-endian)."""
    MAGIC = b"PS-X EXE"
    HEADER_SIZE = 0x800

    def __init__(self, data, path=None):
        self.data = data
        self.path = path
        self.valid_magic = data[:8] == self.MAGIC
        if len(data) >= 0x4C:
            (self.pc, self.gp, self.load_addr, self.text_size,
             self.data_addr, self.data_size, self.bss_addr, self.bss_size,
             self.sp_base, self.sp_off) = struct.unpack_from("<10I", data, 0x10)
        else:
            self.pc = self.gp = self.load_addr = self.text_size = 0
            self.data_addr = self.data_size = self.bss_addr = self.bss_size = 0
            self.sp_base = self.sp_off = 0
        self.region = data[0x4C:0x4C + 0x7B].split(b"\0")[0].decode("ascii", "replace")

    @classmethod
    def load(cls, path):
        with open(path, "rb") as f:
            return cls(f.read(), path)

    @property
    def code(self):
        return self.data[self.HEADER_SIZE:self.HEADER_SIZE + self.text_size]

    def problems(self):
        """List of human-readable header problems (empty == header looks sane)."""
        p = []
        if not self.valid_magic:
            p.append("missing 'PS-X EXE' magic at offset 0")
        if len(self.data) < self.HEADER_SIZE:
            p.append(f"file is {len(self.data)} bytes; a PSX-EXE needs at least a 2048-byte header")
        if self.text_size % 2048:
            p.append(f"text size 0x{self.text_size:X} is not a multiple of 2048")
        if self.HEADER_SIZE + self.text_size > len(self.data):
            p.append("text size runs past end of file")
        if not (0x80000000 <= self.load_addr < 0x80800000):
            p.append(f"load address 0x{self.load_addr:08X} is outside KSEG0 RAM")
        if not (self.load_addr <= self.pc < self.load_addr + max(self.text_size, 4)):
            p.append(f"initial PC 0x{self.pc:08X} is outside the loaded image")
        return p

    def file_offset(self, addr):
        return self.HEADER_SIZE + (addr - self.load_addr)

    def patched(self, addr, blob):
        """Return a copy of the file with `blob` written at memory address `addr`."""
        off = self.file_offset(addr)
        if off < self.HEADER_SIZE or off + len(blob) > len(self.data):
            raise ValueError(f"patch at 0x{addr:08X} (+{len(blob)}) is outside the loaded image")
        b = bytearray(self.data)
        b[off:off + len(blob)] = blob
        return bytes(b)

    def disassemble(self, objdump="mipsel-none-elf-objdump"):
        """Disassemble the text segment. Returns list[Insn]. Data words that are
        not valid instructions appear as `.word`."""
        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".bin") as t:
            t.write(self.code)
            t.flush()
            out = subprocess.run(
                [objdump, "-D", "-b", "binary", "-m", "mips:3000", "-EL",
                 f"--adjust-vma=0x{self.load_addr:08x}", "-M", "gpr-names=32", t.name],
                capture_output=True, text=True, check=True).stdout
        insns = []
        for line in out.splitlines():
            m = re.match(r"\s*([0-9a-f]+):\s+([0-9a-f]{8})\s+(.*)$", line)
            if m:
                insns.append(Insn(int(m.group(1), 16), int(m.group(2), 16),
                                  re.sub(r"\s+", " ", m.group(3)).strip()))
        return insns


def mnemonic(insn):
    """First token of the disassembly text (e.g. 'addiu')."""
    return insn.text.split(" ", 1)[0]
