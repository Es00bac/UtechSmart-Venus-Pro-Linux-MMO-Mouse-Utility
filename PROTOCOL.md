# UtechSmart Venus Pro USB HID Protocol

This is the single source of truth for the Venus Pro configuration protocol, derived
from captures and the current `venus_protocol.py` implementation. Wired and wireless
mode share the same configuration format and commands.

## Device IDs and Interfaces

- **Vendor IDs**: `0x25A7`, `0x04D9`
- **Product IDs**:
  - `0xFA07` = Venus Pro Wireless Receiver (2.4GHz dongle)
  - `0xFA08` = Venus Pro Wired (dual mode mouse via USB)
  - `0xFC55` = Venus MMO Wired

- Configuration is sent as HID **Feature Reports** on the vendor interface.
  - Interface `1` is the preferred config interface.
  - Interface `0` is accepted on some firmware; the code will try both.

## Report Format

All configuration packets are 17 bytes:

```
Byte 0  : Report ID (0x08)
Byte 1  : Command ID
Byte 2-15 : Payload (14 bytes)
Byte 16 : Checksum
```

Checksum calculation (sum of bytes 0..15 must equal 0x55):
```python
checksum = (0x55 - sum(bytes[0:16])) & 0xFF
```

Responses arrive as Report ID `0x09`, echoing the command. For reads (`0x08`),
the response payload includes `[page][offset][len][data...]`.

## Command Summary

| Cmd | Description |
|-----|-------------|
| `0x03` | Handshake / ready |
| `0x04` | Prepare / commit (sent before and after write sequences) |
| `0x07` | Write flash (page/offset addressing) |
| `0x08` | Read flash |
| `0x09` | Reset to defaults |
| `0x4D`, `0x01` | Magic unlock sequence for macro/page-3 writes |

Typical write flow:
1. `0x03` (handshake)
2. One or more `0x07` writes
3. `0x04` (commit)

## Addressing and Profiles

Flash is 256 pages × 256 bytes. Write/read payloads use:
```
[0x00, page, offset, length, data...]
```

For `0x07` writes, `length` is typically ≤ 10 bytes; larger writes require multiple packets.

**Profile Base Offsets** (add to page number for profile-specific data):
- Profile 1: `0x00`
- Profile 2: `0x40`
- Profile 3: `0x80`
- Profile 4: `0xC0`

## Button Map

Each button has:
- **Keyboard definition slot**: `code_hi` (page), `code_lo` (offset within page)
- **Apply slot**: `apply_offset` in Page `0x00 + profile_base`

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
| 14 | Left Mouse Button | 0x01 | 0xE0 | 0x7C |
| 15 | Middle Mouse Button | 0x02 | 0x40 | 0x88 |
| 16 | Right Mouse Button | 0x01 | 0xC0 | 0x78 |

## Button Type Codes

| Type | Value | Description |
|------|-------|-------------|
| Disabled | `0x00` | Button does nothing |
| Mouse | `0x01` | Mouse button (d1 = button mask) |
| DPI Legacy | `0x02` | DPI control |
| Special | `0x04` | Fire Key / Triple Click (d1 = delay, d2 = repeat) |
| Keyboard | `0x05` | Standard keyboard key |
| Macro | `0x06` | Macro (d1 = index, d2 = repeat mode) |
| Poll Rate Toggle | `0x07` | Toggle polling rate |
| RGB Toggle | `0x08` | Toggle RGB LED |

**Mouse Button Masks (Type 0x01):**
- `0x01` = Left Click
- `0x02` = Right Click
- `0x04` = Middle Click
- `0x08` = Back
- `0x10` = Forward

## Keyboard Definition Slots

Keyboard slots are stored at `code_hi + profile_base` page, `code_lo` offset, in 0x20-byte blocks.

**Simple key (no modifiers):**
```
count = 2
events: [0x81, key, 0x00] [0x41, key, 0x00]
guard = (0x91 - (key * 2)) & 0xFF
```

**Key with modifier:**
```
count = 4
events: [0x80, mod, 0x00] [0x81, key, 0x00] [0x40, mod, 0x00] [0x41, key, 0x00]
guard = (0x91 - (key * 2) + 0x3A) & 0xFF
```

**Modifier Bit Flags:**
- `0x01` = Ctrl
- `0x02` = Shift
- `0x04` = Alt
- `0x08` = Win/GUI

## Macro Storage

Macro slots are 384 bytes (0x180) each, starting at page `0x03`:
```python
slot_addr = 0x300 + (index * 0x180)
page = slot_addr >> 8
offset = slot_addr & 0xFF
```

**Macro Buffer Layout:**
| Offset | Size | Description |
|--------|------|-------------|
| 0x00 | 1 | Name length (bytes, UTF-16LE) |
| 0x01-0x1E | 30 | Name bytes (UTF-16LE, ~15 chars) |
| 0x1F | 1 | Event count |
| 0x20+ | 5 each | Events |

**Event Format (5 bytes):**
```
[status] [keycode] [00] [delay_hi] [delay_lo]
```
- `0x81` = Key down
- `0x41` = Key up
- `0x80` = Modifier down
- `0x40` = Modifier up

**Macro Terminator (6 bytes):**
```
[00] [03] [checksum] [00] [00] [00]
```
Checksum: `(~sum(events) - event_count + 0x56) & 0xFF`

**Macro Repeat Modes:**
| Value | Mode |
|-------|------|
| `0x01` | Play once |
| `0x02`-`0xFD` | Repeat N times |
| `0xFE` | Repeat while held |
| `0xFF` | Toggle on/off |

## DPI Configuration

DPI uses linear interpolation between known reference points:

| DPI | Value | Tweak |
|-----|-------|-------|
| 1000 | 0x0B | 0x3F |
| 2000 | 0x17 | 0x27 |
| 4000 | 0x2F | 0xF7 |
| 8000 | 0x5F | 0x97 |
| 10000 | 0xBD | 0xDB |

**Tweak Calculation:**
```python
tweak = (0x55 - (value * 2)) & 0xFF
```

**DPI Slot Addresses:**
Five slots at page `0x00 + profile_base`, offsets `0x0C`, `0x10`, `0x14`, `0x18`, `0x1C`.

## Polling Rate

Polling rate is stored at page `0x00 + profile_base`, offset `0x00`:

| Rate (Hz) | Code | Guard |
|-----------|------|-------|
| 125 | 0x04 | 0x51 |
| 250 | 0x02 | 0x53 |
| 500 | 0x01 | 0x54 |
| 1000 | 0x00 | 0x55 |

**Packet format:**
```
[00, 00, 00, 02, rate_code, rate_guard, 00...]
```

## RGB / Lighting

RGB uses different packet formats depending on mode:

**Mode Constants:**
| Mode | Value |
|------|-------|
| Off | `0x00` |
| Steady | `0x01` |
| Neon | `0x02` |
| Breathing | `0x03` |

**Steady/Neon (offset 0x54):**
```
[00, 00, 54, 08, R, G, B, ColorChk, Mode, 54, B1, B2, 00, 00]
```
- `ColorChk = (0x55 - (R + G + B)) & 0xFF`
- `B1 = brightness * 3` (capped 1-255)
- `B2 = (0x55 - B1) & 0xFF`
- Mode: `0x01` for Steady, `0x02` for Neon

**Breathing (offset 0x5C):**
```
[00, 00, 5C, 02, 03, 52, 00, 00, 00, 00, 00, 00, 00, 00]
```
(Fixed format, cycles through colors)

**Off (offset 0x58):**
```
[00, 00, 58, 02, 00, 55, 00, 00, 00, 00, 00, 00, 00, 00]
```

## Media Key Codes

Media keys use USB HID Consumer Page codes:

| Function | Code |
|----------|------|
| Play/Pause | 0xCD |
| Next Track | 0xB5 |
| Prev Track | 0xB6 |
| Mute | 0xE2 |
| Volume Up | 0xE9 |
| Volume Down | 0xEA |
