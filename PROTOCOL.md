# UtechSmart Venus Pro (Wireless) USB Protocol Notes

This document summarizes what can be inferred from the provided USBPcap captures.
Everything here is based on observed traffic; unknown fields are called out.

## Device IDs
- Vendor ID: `0x25A7`
- Product IDs observed:
  - `0xFA07` (mouse)
  - `0xFA08` (wireless receiver)

## Transport
- USB HID class interface.
- Configuration updates are sent as **HID Set_Report (Feature)** requests.
- Report ID is always `0x08`.
- Observed `wIndex` for Set_Report is `1` (interface 1).

## Report Format
All configuration reports are **17 bytes**:

```
Byte 0  : Report ID (0x08)
Byte 1  : Command ID
Byte 2-15 : Payload (14 bytes)
Byte 16 : Checksum
```

### Checksum
Checksum is computed over bytes 0-15 (report ID + command + payload):

```
checksum = (0x55 - sum(bytes[0..15])) & 0xFF
```

This matches all observed packets.

## Command IDs (Observed)
- `0x03` : Session start / begin write (payload all zeroes)
- `0x04` : Session commit / end write (payload all zeroes)
- `0x07` : Configuration write (payload varies by feature)
- `0x09` : Reset to defaults (payload all zeroes)

The exact semantics of `0x03` and `0x04` are inferred from usage patterns.

### Command 0x07 Addressing
For writes, the first three payload bytes encode a flash address:

```
payload[0] = 0x00
payload[1] = page
payload[2] = offset
payload[3..] = data (11 bytes)
```

This matches the addresses seen in CLAUDE_PROTOCOL.md and the USB captures.

## Button Numbering (Image Reference)
- Buttons 1-12: thumb keypad (side buttons)
- Button 13: upper side button (above the keypad)
- Button 14: left click
- Button 15: middle click (wheel)
- Button 16: right click

## Button Binding (Keyboard)
Observed for binding button 1 to `A`, button 2 to `B`, button 12 to `L`.

### Button Codes (Observed)
The mouse has 16 configurable buttons. Based on CLAUDE_PROTOCOL.md (flash layout) and
captures, side buttons 1-12 map to contiguous keyboard + mouse regions. Buttons 13-16
still need confirmed mappings.

Side button mapping (keyboard page/offset + mouse region offset):

| Button | Page | Offset | Mouse Offset |
|--------|------|--------|--------------|
| 1      | 01   | 00     | 60           |
| 2      | 01   | 20     | 64           |
| 3      | 01   | 40     | 68           |
| 4      | 01   | 60     | 6C           |
| 5      | 01   | 80     | 70           |
| 6      | 01   | A0     | 74           |
| 7      | 02   | 40     | 88           |
| 8      | 02   | 60     | 8C           |
| 9      | 02   | 80     | 90           |
| 10     | 02   | A0     | 94           |
| 11     | 02   | C0     | 98           |
| 12     | 02   | E0     | 9C           |

Buttons 13-16 (upper side and left/middle/right clicks) are still unknown and need
captures to fill in.

### Keyboard binding packet
Command `0x07`, payload bytes (index 2-15):

```
00
<code_hi> <code_lo>
08 02 81
<hid_key> 00 41 <hid_key> 00
<guard> 00 00
```

`<guard>` appears to be `0x91 - (2 * hid_key)` (fits A/B/L).

### Apply binding packet
Command `0x07`, payload bytes (index 2-15):

```
00 00 <apply_offset> 04 05 00 00 50 00 00 00 00 00 00
```

The `0x05` action type and `0x50` action code were seen for keyboard binds.

## Forward / Back
Observed for button 1 (Forward) and button 2 (Back).

### Forward
Payload (index 2-15):

```
00 00 <apply_offset> 04 01 10 00 44 00 00 00 00 00 00
```

### Back
Payload (index 2-15):

```
00 00 <apply_offset> 04 01 08 00 4C 00 00 00 00 00 00
```

## Macro Upload
Macro data is uploaded as a sequence of `0x07` packets with a chunked buffer.

### Macro chunk packet
Payload bytes (index 2-15):

```
00 03 <offset> <chunk_len> <data[10 bytes]>
```

- Offsets increment by `0x0A` (10 bytes).
- `chunk_len` is usually `0x0A`, but the final chunk can be shorter.

### Macro buffer layout (observed)
- Offset `0x00`: one byte = UTF-16LE name length in bytes.
- Offset `0x01..`: UTF-16LE name bytes.
- Offset `0x1E..`: macro event data (format unknown).
- Offset `0x64`: tail bytes (observed `00 03 69 00 00 00`).

### Macro bind packet
Assigns macro index `0x01` to a button (observed for side button 1).

Payload bytes (index 2-15):

```
00 00 <apply_offset> 04 06 00 01 4E 00 00 00 00 00 00
```

`0x06` appears to represent a macro action type.

## DPI Slots
Five slots are updated using command `0x07`.

Payload bytes (index 2-15):

```
00 00 <slot_offset> 04 <val> <val> 00 <tweak> 00 00 00 00 00 00
```

`slot_offset` observed as `0x0C + slot_index * 4` (`slot_index` 0..4).

Observed mapping from UI DPI values to `<val>` and `<tweak>`:

| DPI  | val | tweak |
|------|-----|-------|
| 1600 | 12  | 31    |
| 2400 | 1B  | 1F    |
| 4900 | 3A  | E1    |
| 8900 | 6A  | 81    |
| 14100| A8  | 05    |

The exact conversion from DPI to `<val>/<tweak>` is unknown.

## Polling Rate
Command `0x07`, payload bytes (index 2-15):

```
00 00 00 02 <rate_id> <rate_guard> 00 00 00 00 00 00 00 00
```

Observed values:

| Rate | rate_id | rate_guard |
|------|---------|------------|
| 250  | 04      | 51         |
| 500  | 02      | 53         |
| 1000 | 01      | 54         |

## RGB / Lighting
Lighting changes use command `0x07` and appear to have multiple sub-modes.

### Steady (magenta)
```
00 00 54 08 FF 00 FF 57 01 54 3C 19 00 00
```

### Steady (red, 20%)
```
00 00 54 08 FF 00 00 56 01 54 3C 19 00 00
```

### Steady (red, low)
```
00 00 54 08 FF 00 00 56 01 54 01 54 00 00
```

### Steady (red, high)
```
00 00 54 08 FF 00 00 56 01 54 FF 56 00 00
```

### Neon (magenta)
```
00 00 54 08 FF 00 FF 57 02 53 3C 19 00 00
```

### Breathing (magenta)
```
00 00 5C 02 03 52 00 00 00 00 00 00 00 00
```

### Off
```
00 00 58 02 00 55 00 00 00 00 00 00 00 00
```

The meaning of several RGB bytes (guards, brightness fields, and mode flags) is
still unknown; the above payloads are copied directly from captures.
