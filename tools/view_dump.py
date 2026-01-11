#!/usr/bin/env python3
"""
Colorized Memory Dump Viewer for UtechSmart Venus Pro Mouse
COMPLETE coverage - every byte is shown and analyzed.
"""
from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import sys
import os

# ANSI Color codes
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Distinct colors for each field type
    POLL_RATE = "\033[38;5;39m"     # Bright Blue
    DPI = "\033[38;5;33m"           # Blue
    DPI_COUNT = "\033[38;5;27m"     # Dark Blue
    RGB_R = "\033[38;5;196m"        # Red
    RGB_G = "\033[38;5;46m"         # Green  
    RGB_B = "\033[38;5;21m"         # Blue
    RGB_MODE = "\033[38;5;201m"     # Magenta
    RGB_BRIGHT = "\033[38;5;226m"   # Yellow
    TYPE = "\033[38;5;214m"         # Orange
    MODIFIER = "\033[38;5;201m"     # Magenta
    KEY = "\033[38;5;118m"          # Bright Green
    GUARD = "\033[38;5;81m"         # Cyan
    EVENT_DN = "\033[38;5;226m"     # Yellow (key/mod down)
    EVENT_UP = "\033[38;5;208m"     # Orange (key/mod up)
    DELAY = "\033[38;5;147m"        # Light Purple (delay bytes)
    MACRO_HDR = "\033[38;5;135m"    # Purple (macro header)
    MACRO_NAME = "\033[38;5;183m"   # Light Pink (macro name chars)
    MACRO_LEN = "\033[38;5;141m"    # Light Purple (event count)
    MOUSE_BTN = "\033[38;5;159m"    # Light Cyan
    FIRE = "\033[38;5;202m"         # Dark Orange
    UNKNOWN = "\033[38;5;250m"      # Light Gray (unknown non-empty)
    UNUSED = "\033[38;5;238m"       # Dark Gray (0xFF)
    ZERO = "\033[38;5;236m"         # Very Dark Gray (0x00)
    HEADER = "\033[38;5;255m"       # White

# HID Key lookup (comprehensive)
HID_KEYS = {
    0x04: 'A', 0x05: 'B', 0x06: 'C', 0x07: 'D', 0x08: 'E', 0x09: 'F',
    0x0A: 'G', 0x0B: 'H', 0x0C: 'I', 0x0D: 'J', 0x0E: 'K', 0x0F: 'L',
    0x10: 'M', 0x11: 'N', 0x12: 'O', 0x13: 'P', 0x14: 'Q', 0x15: 'R',
    0x16: 'S', 0x17: 'T', 0x18: 'U', 0x19: 'V', 0x1A: 'W', 0x1B: 'X',
    0x1C: 'Y', 0x1D: 'Z', 0x1E: '1', 0x1F: '2', 0x20: '3', 0x21: '4',
    0x22: '5', 0x23: '6', 0x24: '7', 0x25: '8', 0x26: '9', 0x27: '0',
    0x28: 'Ent', 0x29: 'Esc', 0x2A: 'Bks', 0x2B: 'Tab', 0x2C: 'Spc',
    0x2D: '-', 0x2E: '=', 0x2F: '[', 0x30: ']', 0x31: '\\', 0x33: ';',
    0x34: "'", 0x35: '`', 0x36: ',', 0x37: '.', 0x38: '/', 0x39: 'Cap',
    0x3A: 'F1', 0x3B: 'F2', 0x3C: 'F3', 0x3D: 'F4', 0x3E: 'F5', 0x3F: 'F6',
    0x40: 'F7', 0x41: 'F8', 0x42: 'F9', 0x43: 'F10', 0x44: 'F11', 0x45: 'F12',
    0x46: 'PrS', 0x47: 'ScL', 0x48: 'Pau', 0x49: 'Ins', 0x4A: 'Hom',
    0x4B: 'PgU', 0x4C: 'Del', 0x4D: 'End', 0x4E: 'PgD', 0x4F: '→',
    0x50: '←', 0x51: '↓', 0x52: '↑', 0x53: 'Num', 0x54: 'Kp/', 0x55: 'Kp*',
    0x56: 'Kp-', 0x57: 'Kp+',
}

BINDING_TYPES = {
    0x00: "Disabled", 0x01: "Mouse", 0x02: "Keyboard", 0x03: "Media",
    0x04: "FireKey", 0x05: "KbdDefault", 0x06: "Macro", 0x07: "DPIToggle",
    0x08: "DPIUpDn", 0x13: "DPILock",
}

MODIFIER_NAMES = {
    0x01: "Ctrl", 0x02: "Shft", 0x03: "C+S", 0x04: "Alt", 0x05: "C+A",
    0x06: "S+A", 0x07: "CSA", 0x08: "Win", 0x10: "LSh", 0x20: "RSh",
}

MOUSE_BUTTONS = {0x01: "LClk", 0x02: "RClk", 0x04: "MClk", 0x08: "Back", 0x10: "Fwd"}

EVENT_CODES = {0x80: "M↓", 0x81: "K↓", 0x40: "M↑", 0x41: "K↑"}

POLLING_RATES = {0x01: "1000Hz", 0x02: "500Hz", 0x04: "250Hz", 0x08: "125Hz"}

def col(byte: int, color: str) -> str:
    """Colorize a single byte."""
    return f"{color}{byte:02x}{C.RESET}"

def get_page_type(page_num: int) -> tuple[str, int]:
    """Determine page type and profile number."""
    if page_num < 0x80:
        profile = 1
        base = 0
    elif page_num < 0xC0:
        profile = 2
        base = 0x80
    else:
        profile = 3
        base = 0xC0
    
    rel = page_num - base
    if rel == 0:
        return "Config", profile
    elif rel in (1, 2):
        return "KbdData", profile
    elif rel < 0x40:
        return "Macro", profile
    else:
        return "Unknown", profile

class DumpViewer:
    def __init__(self, data: bytearray, page_num: int):
        self.data = data
        self.page = page_num
        self.page_type, self.profile = get_page_type(page_num)
        self.annotations = {}  # offset -> annotation string
        
    def analyze(self):
        """Pre-analyze the page to generate all annotations."""
        if self.page_type == "Config":
            self._analyze_config()
        elif self.page_type == "KbdData":
            self._analyze_kbd()
        elif self.page_type == "Macro":
            self._analyze_macro()
    
    def _analyze_config(self):
        """Analyze configuration page (0x00, 0x80, 0xC0)."""
        d = self.data
        
        # Polling rate
        self.annotations[0x00] = f"PollRate={POLLING_RATES.get(d[0], '?')}"
        self.annotations[0x01] = "Unk01"
        self.annotations[0x02] = f"DPIStages={d[2]}"
        self.annotations[0x03] = "Unk03"
        
        # DPI stages (0x04-0x2F, pairs)
        for i, off in enumerate(range(0x04, 0x30, 2)):
            stage = i + 1
            if off + 1 < len(d):
                dpi_val = d[off] | (d[off+1] << 8)
                self.annotations[off] = f"DPI{stage}L"
                self.annotations[off+1] = f"DPI{stage}H={dpi_val}"
        
        # RGB region (0x30-0x53)
        for off in range(0x30, 0x54):
            self.annotations[off] = "RGB"
            
        # LED Config (0x54-0x5B)
        self.annotations[0x54] = f"LEDMode={d[0x54]:02X}"
        self.annotations[0x55] = f"Bright={int(d[0x55]/255*100)}%"
        self.annotations[0x56] = "LEDSpd"
        self.annotations[0x57] = "LEDDir"
        self.annotations[0x58] = f"R={d[0x58]}"
        self.annotations[0x59] = f"G={d[0x59]}"
        self.annotations[0x5A] = f"B={d[0x5A]}"
        for off in range(0x5B, 0x60):
            self.annotations[off] = "LEDPad"
        
        # Button bindings (0x60-0xAF)
        btn_map = {
            0x60: "B1", 0x64: "B2", 0x68: "B3", 0x6C: "B4",
            0x70: "B5", 0x74: "B6", 0x78: "B16", 0x7C: "B14",
            0x80: "B7", 0x84: "B8", 0x88: "B15", 0x8C: "B13",
            0x90: "B9", 0x94: "B10", 0x98: "B11", 0x9C: "B12",
            0xA0: "BA", 0xA4: "BB", 0xA8: "BC", 0xAC: "BD",
        }
        for base, name in btn_map.items():
            if base + 3 < len(d):
                btype = d[base]
                type_name = BINDING_TYPES.get(btype, f"T{btype:02X}")
                mod = d[base+1]
                mod_name = MODIFIER_NAMES.get(mod, "") if mod else ""
                
                self.annotations[base] = f"{name}.Type={type_name}"
                self.annotations[base+1] = f"{name}.D1" + (f"={mod_name}" if mod_name else f"={mod:02X}" if mod else "")
                self.annotations[base+2] = f"{name}.D2={d[base+2]:02X}" if d[base+2] else f"{name}.D2"
                self.annotations[base+3] = f"{name}.Chk"
    
    def _analyze_kbd(self):
        """Analyze keyboard data pages (0x01-0x02, etc.)."""
        d = self.data
        slots = {0x00: "B1", 0x20: "B2", 0x40: "B3", 0x60: "B4",
                 0x80: "B5", 0xA0: "B6", 0xC0: "B7", 0xE0: "B11"}
        
        for base, name in slots.items():
            if base >= len(d):
                continue
            count = d[base]
            if count == 0xFF:
                self.annotations[base] = f"{name}.Empty"
                continue
                
            self.annotations[base] = f"{name}.Cnt={count}"
            
            # Parse events (3 bytes each: Code, Val, Pad)
            pos = base + 1
            evt_num = 0
            while pos < base + 8 and pos + 2 < len(d):
                code = d[pos]
                val = d[pos+1]
                pad = d[pos+2]
                
                if code == 0xFF:
                    break
                    
                evt_num += 1
                code_name = EVENT_CODES.get(code, f"{code:02X}")
                if code in (0x81, 0x41):  # Key events
                    val_name = HID_KEYS.get(val, f"K{val:02X}")
                else:  # Mod events
                    val_name = MODIFIER_NAMES.get(val, f"M{val:02X}")
                
                self.annotations[pos] = f"{name}.E{evt_num}={code_name}"
                self.annotations[pos+1] = f"={val_name}"
                self.annotations[pos+2] = "Pad" if pad == 0 else f"M{pad:02X}"
                pos += 3
            
            # Guard byte
            if base + 7 < len(d):
                self.annotations[base+7] = f"{name}.Guard"
    
    def _analyze_macro(self):
        """Analyze macro storage pages.
        
        Corrected format (after bug fix):
        - Byte 0: Slot Index (0-11)
        - Bytes 1-28: Name in UTF-16LE (up to 14 chars)
        - Bytes 29-30: Padding (zeros)
        - Byte 0x1F (31): Event count
        - Bytes 0x20+: Macro events (5 bytes each: EventCode, Key, 0x00, DelayHi, DelayLo)
        """
        d = self.data
        
        # Look for macro headers: [SlotNum] [NameBytes...] [00 padding to 0x1F] [EventCount at 0x1F]
        # Macros can start at 0x00 or 0x80 within a page
        for macro_base in [0x00, 0x80]:
            if macro_base >= len(d):
                continue
            
            slot = d[macro_base]
            if slot == 0xFF:
                self.annotations[macro_base] = "MacroEmpty"
                continue
            
            self.annotations[macro_base] = f"Macro.Slot={slot}"
            
            # Name (UTF-16LE, 2 bytes per char, up to 14 chars = 28 bytes)
            name_chars = []
            for i in range(1, 29, 2):
                if macro_base + i + 1 < len(d):
                    lo = d[macro_base + i]
                    hi = d[macro_base + i + 1]
                    if lo == 0 and hi == 0:
                        break
                    char = chr(lo | (hi << 8))
                    if char.isprintable():
                        name_chars.append(char)
                    self.annotations[macro_base + i] = f"Name.{len(name_chars)}"
                    self.annotations[macro_base + i + 1] = ""
            
            if name_chars:
                self.annotations[macro_base + 1] = f"Name=\"{''.join(name_chars)}\""
            
            # Event count at offset 0x1F from base
            if macro_base + 0x1F < len(d):
                evt_count = d[macro_base + 0x1F]
                self.annotations[macro_base + 0x1F] = f"EvtCnt={evt_count}"
            
            # Macro events start at base + 0x20
            # Format: [EventCode] [Key] [00] [DelayHi] [DelayLo] = 5 bytes per event
            evt_base = macro_base + 0x20
            evt_num = 0
            while evt_base + 4 < len(d) and evt_base < macro_base + 0x80:
                code = d[evt_base]
                if code == 0xFF or code == 0x00:
                    break
                
                key = d[evt_base + 1]
                pad = d[evt_base + 2]
                delay_hi = d[evt_base + 3]
                delay_lo = d[evt_base + 4]
                delay = (delay_hi << 8) | delay_lo
                
                evt_num += 1
                code_name = EVENT_CODES.get(code, f"E{code:02X}")
                if code in (0x81, 0x41):
                    val_name = HID_KEYS.get(key, f"K{key:02X}")
                else:
                    val_name = MODIFIER_NAMES.get(key, f"M{key:02X}")
                
                self.annotations[evt_base] = f"M{evt_num}.{code_name}"
                self.annotations[evt_base + 1] = f"={val_name}"
                self.annotations[evt_base + 2] = ""
                self.annotations[evt_base + 3] = f"D={delay}ms" if delay_hi else ""
                self.annotations[evt_base + 4] = "" if delay_hi else f"D={delay}ms"
                
                evt_base += 5
    
    def get_byte_color(self, offset: int) -> str:
        """Get the appropriate color for a byte based on its meaning."""
        byte = self.data[offset] if offset < len(self.data) else 0
        ann = self.annotations.get(offset, "")
        
        # Special values
        if byte == 0xFF:
            return C.UNUSED
        if byte == 0x00:
            return C.ZERO
        
        # Based on annotation content
        if "PollRate" in ann:
            return C.POLL_RATE
        if "DPI" in ann:
            return C.DPI
        if ann.startswith("R=") or "RGB" in ann:
            return C.RGB_R
        if ann.startswith("G="):
            return C.RGB_G
        if ann.startswith("B="):
            return C.RGB_B
        if "Bright" in ann or "LED" in ann:
            return C.RGB_BRIGHT
        if ".Type=" in ann:
            return C.TYPE
        if ".D1" in ann and "Mod" in ann:
            return C.MODIFIER
        if ".D1" in ann or ".D2" in ann:
            return C.UNKNOWN
        if ".Chk" in ann or "Guard" in ann:
            return C.GUARD
        if "K↓" in ann or "K↑" in ann:
            return C.EVENT_DN if "↓" in ann else C.EVENT_UP
        if "M↓" in ann or "M↑" in ann:
            return C.MODIFIER
        if "=K" in ann or ann in HID_KEYS.values():
            return C.KEY
        if "D=" in ann and "ms" in ann:
            return C.DELAY
        if "Macro" in ann or "Slot=" in ann:
            return C.MACRO_HDR
        if "Name" in ann:
            return C.MACRO_NAME
        if "EvtCnt" in ann:
            return C.MACRO_LEN
        if "M." in ann and ".E" in ann:
            return C.EVENT_DN
        
        return C.UNKNOWN

    def display(self):
        """Display the page with full annotations."""
        self.analyze()
        
        print(f"\n{C.BOLD}{'═' * 130}{C.RESET}")
        print(f"{C.BOLD}PAGE 0x{self.page:02X} - {self.page_type} (Profile {self.profile}){C.RESET}")
        print(f"{C.BOLD}{'═' * 130}{C.RESET}")
        print(f"{C.DIM}Off   0  1  2  3  4  5  6  7  8  9  A  B  C  D  E  F   Annotations{C.RESET}")
        print(f"{'─' * 130}")
        
        for row in range(0, len(self.data), 16):
            # Offset
            line = f"{C.DIM}{row:04x}{C.RESET}  "
            
            # Hex bytes with colors
            for i in range(16):
                off = row + i
                if off < len(self.data):
                    byte = self.data[off]
                    color = self.get_byte_color(off)
                    line += f"{col(byte, color)} "
                else:
                    line += "   "
            
            # Annotations for this row
            line += " "
            anns = []
            for i in range(16):
                off = row + i
                ann = self.annotations.get(off, "")
                if ann and ann not in anns and len(ann) > 0:
                    anns.append(ann)
            
            # Compact annotations
            ann_str = " │ ".join(anns[:5])
            if len(ann_str) > 70:
                ann_str = ann_str[:67] + "..."
            
            line += f"{C.DIM}{ann_str}{C.RESET}"
            print(line)

def print_legend():
    print(f"\n{C.BOLD}Color Legend:{C.RESET}")
    print(f"  {C.POLL_RATE}██{C.RESET} PollRate  {C.DPI}██{C.RESET} DPI  {C.RGB_R}██{C.RESET} R  {C.RGB_G}██{C.RESET} G  {C.RGB_B}██{C.RESET} B  {C.RGB_BRIGHT}██{C.RESET} LED/Bright  {C.TYPE}██{C.RESET} Type")
    print(f"  {C.MODIFIER}██{C.RESET} Modifier  {C.KEY}██{C.RESET} Key  {C.EVENT_DN}██{C.RESET} EvtDn  {C.EVENT_UP}██{C.RESET} EvtUp  {C.GUARD}██{C.RESET} Guard/Chk  {C.DELAY}██{C.RESET} Delay")
    print(f"  {C.MACRO_HDR}██{C.RESET} MacroHdr  {C.MACRO_NAME}██{C.RESET} MacroName  {C.MACRO_LEN}██{C.RESET} EvtCount  {C.UNKNOWN}██{C.RESET} Unknown  {C.UNUSED}██{C.RESET} 0xFF  {C.ZERO}██{C.RESET} 0x00")

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 tools/view_dump.py <dump_dir> [pages...]")
        print("       python3 tools/view_dump.py <dump_dir> all         # View all 256 pages")
        print("       python3 tools/view_dump.py <page.bin>")
        print("\nExamples:")
        print("  python3 tools/view_dump.py 'dumps/Good Config From Windows' 00 01 02 03 80")
        print("  python3 tools/view_dump.py dumps/dump_12345 all")
        sys.exit(1)
    
    path = sys.argv[1]
    
    # Single file mode
    if path.endswith(".bin"):
        with open(path, "rb") as f:
            data = bytearray(f.read())
        page_num = int(os.path.basename(path).split("_")[1].split(".")[0], 16)
        viewer = DumpViewer(data, page_num)
        viewer.display()
        print_legend()
        return
    
    # Directory mode
    if len(sys.argv) > 2:
        if sys.argv[2].lower() == "all":
            pages = list(range(256))
        else:
            pages = []
            for p in sys.argv[2:]:
                try:
                    pages.append(int(p, 16) if any(c in p.lower() for c in "abcdef") else int(p))
                except ValueError:
                    print(f"Invalid page: {p}")
                    sys.exit(1)
    else:
        pages = [0x00, 0x01, 0x02, 0x03]  # Default pages
    
    for page_num in pages:
        bin_path = os.path.join(path, f"page_{page_num:02X}.bin")
        if not os.path.exists(bin_path):
            continue
        
        with open(bin_path, "rb") as f:
            data = bytearray(f.read())
        
        # Skip completely empty pages in "all" mode
        if len(sys.argv) > 2 and sys.argv[2].lower() == "all":
            if all(b == 0xFF for b in data):
                continue
        
        viewer = DumpViewer(data, page_num)
        viewer.display()
    
    print_legend()

if __name__ == "__main__":
    main()
