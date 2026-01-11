# UtechSmart Venus Pro USB HID Protocol

This is the single source of truth for the Venus Pro configuration protocol, derived
from captures and the current `venus_protocol.py` implementation. Wired and wireless
mode share the same configuration format and commands.

## Device IDs and Interfaces
- Vendor ID: `0x25A7`
- Product IDs:
  - `0xFA08` = 2.4G Dual Mode Mouse (wired connection)
  - `0xFA07` = 2.4G Wireless Receiver (wireless dongle)
- Configuration is sent as HID **Feature Reports** on the vendor interface.
  - Interface `1` is the config interface on most firmware.
  - Interface `0` is accepted on some firmware; the code will use either.

## Report Format
All configuration packets are 17 bytes:

```
Byte 0  : Report ID (0x08)
Byte 1  : Command ID
Byte 2-15 : Payload (14 bytes)
Byte 16 : Checksum
```

Checksum (sum of bytes 0..15 must equal 0x55):
```
checksum = (0x55 - sum(bytes[0..15])) & 0xFF
```

Responses arrive as Report ID `0x09`, echoing the command. For reads (`0x08`),
the response payload includes `[page][offset][len][data...]`.

## Command Summary
- `0x03`: Handshake / ready
- `0x04`: Prepare / commit (sent before and after write sequences)
- `0x07`: Write flash (page/offset addressing)
- `0x08`: Read flash
- `0x09`: Reset to defaults
- `0x4D`, `0x01`: Magic unlock sequence for macro/page-3 writes (used by `unlock()`)

Typical write flow:
1. `0x04` (prepare)
2. `0x03` (handshake)
3. One or more `0x07` writes
4. `0x04` (commit)

## Addressing and Profiles
Flash is 256 pages x 256 bytes. Write/read payloads use:
```
[0x00, page, offset, length, data...]
```

For `0x07` writes, `length` is typically <= 0x0A (10 bytes); larger writes are
sent as multiple packets.

Profiles are page-base offsets:
- Profile 1: `0x00`
- Profile 2: `0x40`
- Profile 3: `0x80`
- Profile 4: `0xC0`

When writing profile-specific data, add the base to the page number (e.g., keyboard
page `0x01` becomes `0x41` for Profile 2).

## Button Map
Each button has:
- a **keyboard definition slot** (`code_hi` page, `code_lo` offset)
- an **apply slot** (`apply_offset`) in Page 0x00 + profile base

| Button | Label | code_hi | code_lo | apply_offset |
|--------|-------|---------|---------|--------------|
| 1 | Side Button 1 | 0x01 | 0x00 | 0x60 |
| 2 | Side Button 2 | 0x01 | 0x20 | 0x64 |
| 3 | Side Button 3 | 0x01 | 0x40 | 0x68 |
| 4 | Side Button 4 | 0x01 | 0x60 | 0x6C |
| 5 | Side Button 5 | 0x01 | 0x80 | 0x70 |
| 6 | Side Button 6 | 0x01 | 0xA0 | 0x74 |
| 7 | Side Button 7 | 0x02 | 0x00 | 0x80 |
| 8 | Side Button 8 | 0x02 | 0x20 | 0x84 |
| 9 | Side Button 9 | 0x02 | 0x80 | 0x90 |
| 10 | Side Button 10 | 0x02 | 0xA0 | 0x94 |
| 11 | Side Button 11 | 0x02 | 0xC0 | 0x98 |
| 12 | Side Button 12 | 0x02 | 0xE0 | 0x9C |
| 13 | Fire Key | 0x02 | 0x60 | 0x8C |
| 14 | Left Click | 0x01 | 0xE0 | 0x7C |
| 15 | Middle Click | 0x02 | 0x40 | 0x88 |
| 16 | Right Click | 0x01 | 0xC0 | 0x78 |

## Apply Slot Format (Bindings)
Bindings are 4-byte entries written at the `apply_offset` in page `0x00 + base`:
```
[00, page, offset, 04, type, d1, d2, d3, 00...]
```

Action types (d3 = `0x55 - (type + d1 + d2)` when noted):
- `0x00`: Disabled (d3 = `0x55`)
- `0x01`: Mouse button
  - d1 = button mask (`0x01` left, `0x02` right, `0x04` middle, `0x08` back, `0x10` forward)
  - forward/back captures show d3 = `0x44` / `0x4C` respectively
- `0x02`: DPI control (d1 selects function, d3 = 0x50)
- `0x04`: Special (Fire/Triple) (d1 = delay ms, d2 = repeat count, d3 computed)
- `0x05`: Keyboard (binds to key definition slot, d3 computed)
- `0x06`: Macro (d1 = macro index, d2 = repeat mode, d3 computed)
- `0x07`: Poll rate toggle (d3 computed)
- `0x08`: RGB toggle (d3 computed)

## Keyboard Definition Slots
Keyboard slots are stored at `code_hi + base` / `code_lo` in 0x20-byte blocks.
The payload starts with a count, followed by event triples, and a guard byte:

Simple key (no modifiers):
```
count=2
events: [0x81, key, 0x00] [0x41, key, 0x00]
guard = (0x91 - (key * 2)) & 0xFF
```

Modifier key:
```
count=4
events: [0x80, mod, 0x00] [0x81, key, 0x00] [0x40, mod, 0x00] [0x41, key, 0x00]
guard = (0x91 - (key * 2) + 0x3A) & 0xFF
```

## Macro Storage
Macro slots are 384 bytes each:
```
base = 0x300
slot_addr = base + (index * 0x180)
page = slot_addr >> 8
offset = slot_addr & 0xFF
```

Macro buffer layout:
- `0x00`: UTF-16LE name length (bytes)
- `0x01..0x1E`: name bytes
- `0x1F`: event count
- `0x20..`: events (5 bytes each)

Event format:
```
[status] [keycode] 00 [delay_hi] [delay_lo]
status: 0x81 key down, 0x41 key up, 0x80 mod down, 0x40 mod up
```

Terminator (4 bytes) immediately after the last event:
```
[checksum] 00 00 00
checksum = (~sum(events) - event_count + 0x56) & 0xFF
```

Macro repeat modes:
- `0x01`: play once
- `0xFE`: repeat while held
- `0xFF`: toggle on/off
- `0x01..0xFD`: repeat count

Some firmware requires the unlock sequence (`0x09`, `0x4D`, `0x01`) before macro writes.

## DPI Slots
Five DPI slots live at `offset = 0x0C + (slot * 4)` in page `0x00 + base`:
```
[00, 00, offset, 04, value, value, 00, tweak, 00...]
```

Known mappings used by the current GUI:
| DPI | value | tweak |
|-----|-------|-------|
| 1600 | 0x12 | 0x31 |
| 2400 | 0x1B | 0x1F |
| 4900 | 0x3A | 0xE1 |
| 8900 | 0x6A | 0x81 |
| 14100 | 0xA8 | 0x05 |

## Polling Rate
Polling rate is stored at page `0x00 + base`, offset `0x00`:
```
[00, 00, 00, 02, rate_code, rate_guard, 00...]
```

Observed values:
| Rate | rate_code | rate_guard |
|------|-----------|------------|
| 125 | 0x04 | 0x51 |
| 250 | 0x02 | 0x53 |
| 500 | 0x01 | 0x54 |
| 1000 | 0x00 | 0x55 |

Note: 125 Hz may vary across firmware; some captures hinted at `rate_code=0x03`.

## RGB / Lighting
RGB writes use page `0x00 + base`, offset `0x54`, length `0x08`:
```
[00, 00, 54, 08, R, G, B, mode, 01, 54, b1, b2, 00, 00]
```

Mode byte:
- `0x56`: steady
- `0x57`: animated (breathing/neon)

Brightness encoding:
- `b1 = max(1, min(255, brightness_percent * 3))`
- `b2 = (0x55 - b1) & 0xFF`
