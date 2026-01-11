# UtechSmart Venus Mouse HID Protocol

Reverse-engineered protocol documentation for the UtechSmart Venus Wireless Gaming Mouse.
Based on USB capture analysis from the Windows configuration software (January 2026).

## Device Information

| Device | VID:PID | Description |
|--------|---------|-------------|
| Wireless Receiver | 25A7:FA07 | 2.4GHz wireless dongle |
| Wired Mode | 25A7:FA08 | Direct USB connection |

Both devices expose 2 HID interfaces:
- **Interface 0**: Standard mouse/keyboard HID (input reports)
- **Interface 1**: Vendor-specific configuration (feature reports)

Configuration commands are sent to **Interface 1** via HID Feature Reports.

## HID Report Structure

### Report ID 8 (0x08) - Commands (Host → Device)

All configuration commands use Report ID 8 with a 17-byte payload:

```
Byte 0:     Report ID (0x08)
Bytes 1-15: Command data (15 bytes, zero-padded)
Byte 16:    Checksum
```

### Report ID 9 (0x09) - Responses (Device → Host)

Device responses use Report ID 9, echoing the command with status:

```
Byte 0:     Report ID (0x09)
Bytes 1-15: Response data
Byte 16:    Checksum
```

### Checksum Calculation

```python
def calc_checksum(data_bytes):
    """Sum of all 17 bytes must equal 0x55"""
    return (0x55 - sum(data_bytes[:16])) & 0xFF
```

## Command Reference

### 0x03 - Prepare Flash Write

Sent before any flash write operation. Must be sent before each 0x07 command sequence.

**Request:**
```
08 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 4a
```

**Response:**
```
09 03 00 00 00 01 01 00 00 00 00 00 00 00 00 00 47
```

Bytes 5-6 = `01 01` indicates ready state.

### 0x04 - Query DPI/Status

Read current DPI configuration and device status.

**Request:**
```
08 04 [level] 00 00 00 00 00 00 00 00 00 00 00 00 00 [chk]
```

**Response:**
```
09 04 [level] 00 00 [dpi_idx] [dpi_lo] [dpi_hi] 00 00 00 00 00 00 00 00 [chk]
```

### 0x05 - Set LED Configuration

**Request:**
```
08 05 [mode] [brightness] [speed] [R] [G] [B] 00 00 00 00 00 00 00 00 [chk]
```

| Field | Values |
|-------|--------|
| mode | 0x00=Off, 0x01=Steady, 0x02=Breathing, 0x03=Neon, etc. |
| brightness | 0x00-0x64 (0-100%) |
| speed | 0x00-0x04 (for animated modes) |
| R, G, B | 0x00-0xFF |

### 0x06 - Read Button Configuration (RAM)

Read current button binding from RAM.

**Request:**
```
08 06 [firmware_index] 00 00 00 00 00 00 00 00 00 00 00 00 00 [chk]
```

**Response:**
```
09 06 [firmware_index] [type] [code] [mod_lo] [mod_hi] 00 00 00 00 00 00 00 00 [chk]
```

**Note:** This reads from RAM, not flash. After writing to flash, RAM may not be updated until device restart.

### 0x07 - Write to Flash Memory

Direct flash memory write. This is the primary command for persistent configuration.

**Request:**
```
08 07 00 [page] [offset] [data...11 bytes] [chk]
```

The address is 3 bytes: `00 [page] [offset]`

**Response:** Device echoes the write data back.

### 0x09 - Factory Reset

Reset all settings to factory defaults.

**Request:**
```
08 09 00 00 00 00 00 00 00 00 00 00 00 00 00 00 43
```

## Flash Memory Layout

### Address Format

```
[0x00] [page] [offset]
```

- Byte 0: Always 0x00
- Byte 1: Page number
- Byte 2: Offset within page

### Button Regions

Each button has TWO flash regions that must be written:

1. **Mouse Region** (page 0x00): Defines button type and behavior
2. **Keyboard Region** (pages 0x01+): Stores keyboard macro/key data

### Button to Flash Index Mapping

The mouse has 12 programmable buttons. Flash indices 6-9 are reserved (likely DPI/system buttons).

| Button | Flash Index | Mouse Offset | Kbd Page | Kbd Offset |
|--------|-------------|--------------|----------|------------|
| 1 | 0 | 0x60 | 0x01 | 0x00 |
| 2 | 1 | 0x64 | 0x01 | 0x20 |
| 3 | 2 | 0x68 | 0x01 | 0x40 |
| 4 | 3 | 0x6C | 0x01 | 0x60 |
| 5 | 4 | 0x70 | 0x01 | 0x80 |
| 6 | 5 | 0x74 | 0x01 | 0xA0 |
| 7 | 10 | 0x88 | 0x02 | 0x40 |
| 8 | 11 | 0x8C | 0x02 | 0x60 |
| 9 | 12 | 0x90 | 0x02 | 0x80 |
| 10 | 13 | 0x94 | 0x02 | 0xA0 |
| 11 | 14 | 0x98 | 0x02 | 0xC0 |
| 12 | 15 | 0x9C | 0x02 | 0xE0 |

### Address Calculation

```python
def get_flash_addresses(button_num):
    """Calculate flash addresses for a button (1-12)"""
    # Map button to flash index
    if button_num <= 6:
        flash_index = button_num - 1  # 0-5
    else:
        flash_index = button_num + 3  # 10-15 (skip 6-9)

    # Mouse region: page 0x00, offset 0x60+
    mouse_offset = 0x60 + (flash_index * 4)

    # Keyboard region: page 0x01+, offset in 0x20 increments
    kbd_page = 0x01 + (flash_index // 8)
    kbd_offset = (flash_index % 8) * 0x20

    return {
        'flash_index': flash_index,
        'mouse_page': 0x00,
        'mouse_offset': mouse_offset,
        'kbd_page': kbd_page,
        'kbd_offset': kbd_offset
    }
```

## Button Binding Formats

### Mouse Region Data (11 bytes)

Written to page 0x00, offset calculated per button.

**For Keyboard Binding:**
```
04 05 00 00 50 00 00 00 00 00 00
```
- `04` = Data marker
- `05` = Type: Keyboard
- `50` = Unknown flag

**For Mouse Button Binding:**
```
04 01 [button_code] 00 [extra] 00 00 00 00 00 00
```
- `04` = Data marker
- `01` = Type: Mouse button
- `button_code`: 0x01=Left, 0x02=Right, 0x04=Middle, 0x08=Back, 0x10=Forward
- `extra`: 0x4C for buttons < 0x10, 0x44 for buttons >= 0x10

**For Macro Binding:**
```
04 06 00 00 [flags] 00 00 00 00 00 00
```
- `06` = Type: Macro

### Keyboard Region Data (11 bytes)

Written to pages 0x01+ for keyboard bindings.

```
08 02 81 [keycode] [modifier] 41 [keycode] 00 [mystery] 00 00
```

| Field | Description |
|-------|-------------|
| 08 02 81 | Header bytes |
| keycode | USB HID keycode (e.g., 0x04 = 'A') |
| modifier | Modifier mask (Ctrl=0x01, Shift=0x02, Alt=0x04, GUI=0x08) |
| 41 | Separator |
| keycode | Repeated keycode |
| mystery | Calculated: `(0x91 - (keycode * 2)) & 0xFF` |

### USB HID Keycodes (Common)

| Key | Code | Key | Code |
|-----|------|-----|------|
| A | 0x04 | 1 | 0x1E |
| B | 0x05 | 2 | 0x1F |
| C | 0x06 | 3 | 0x20 |
| ... | ... | ... | ... |
| Z | 0x1D | 0 | 0x27 |

## Complete Write Sequence

To rebind a button to a keyboard key:

```python
# Example: Set button 1 to 'A' (keycode 0x04)
flash_index = 0
keycode = 0x04

# Step 1: Send prepare command
send([0x08, 0x03, 0x00, ...zeros..., 0x4a])
wait(300ms)

# Step 2: Write keyboard region
mystery = (0x91 - (keycode * 2)) & 0xFF  # = 0x89
kbd_data = [0x08, 0x07, 0x00, 0x01, 0x00,  # page=0x01, offset=0x00
            0x08, 0x02, 0x81, keycode, 0x00, 0x41, keycode, 0x00, mystery, 0x00, 0x00]
send(kbd_data + [checksum])
wait(300ms)

# Step 3: Write mouse region
mouse_data = [0x08, 0x07, 0x00, 0x00, 0x60,  # page=0x00, offset=0x60
              0x04, 0x05, 0x00, 0x00, 0x50, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
send(mouse_data + [checksum])
wait(300ms)
```

## DPI Configuration

DPI levels are stored at page 0x00, offsets 0x0C-0x1C (5 levels, 4 bytes each).

**Write format:**
```
08 07 00 00 [offset] 04 [dpi_byte] [dpi_byte] 00 [validation] 00 00 00 00 00 00 [chk]
```

| DPI Level | Offset | Example DPI | DPI Byte |
|-----------|--------|-------------|----------|
| 1 | 0x0C | 1600 | 0x12 (18) |
| 2 | 0x10 | 2400 | 0x1B (27) |
| 3 | 0x14 | 4900 | 0x3A (58) |
| 4 | 0x18 | 8900 | 0x6A (106) |
| 5 | 0x1C | 14100 | 0xA8 (168) |

The DPI byte appears twice in the packet. The validation byte follows a checksum pattern.

## Polling Rate Configuration

**Location:** Page 0x00, Offset 0x00

**Formula:**
```python
code = int(math.log2(1000 / rate_hz))
# 125Hz → 0x04, 250Hz → 0x02, 500Hz → 0x01, 1000Hz → 0x00
```

| Rate (Hz) | Interval (ms) | Code |
|-----------|---------------|------|
| 125 | 8 | 0x04 |
| 250 | 4 | 0x02 |
| 500 | 2 | 0x01 |
| 1000 | 1 | 0x00 |

**Packet:**
```
08 07 00 00 00 02 [CODE] [VALIDATION] 00 00 00 00 00 00 00 00 [CHK]
```

## LED Brightness Encoding

Brightness uses a **checksum-based validation** at offset 0x54:

```
Constraint: B1 + B2 = 0x55 (85 decimal)
B1 = percent × 3, capped at 255 (min 1)
B2 = (0x55 - B1) & 0xFF
```

| Brightness % | B1 | B2 |
|--------------|------|------|
| 0% | 0x01 | 0x54 |
| 10% | 0x1e | 0x37 |
| 20% | 0x3c | 0x19 |
| 100% | 0xff | 0x56 |

**LED Mode Codes:**
- 0x56 = Steady (solid color)
- 0x57 = Neon (rainbow cycle)

**Full LED packet:**
```
08 07 00 00 54 08 [R] [G] [B] [MODE] 01 54 [B1] [B2] 00 00 [CHK]
```

## Special Button Types

| Type Code | Function |
|-----------|----------|
| 0x00 | Disabled |
| 0x01 | Mouse Button |
| 0x04 | Special (Fire Key, Triple Click) |
| 0x05 | Media Key (requires keyboard region) |
| 0x06 | Macro |
| 0x07 | Polling Rate Toggle |
| 0x08 | RGB LED Toggle |

### Macro Repeat Modes
The binding packet for a macro includes a flag byte that determines its repeat behavior:

| Flag | Mode | Description |
|------|------|-------------|
| `0x01` - `0x7F` | Run N Times | Run the macro once (0x01) or up to 127 times. |
| `0xFE` | Repeat While Held | Loops the macro continuously as long as the button is depressed. |
| `0xFF` | Loop Until New Key | Loops until any other key or mouse button is pressed. |

### Macro Memory Slots
Macros are stored in dedicated **384-byte slots** (1.5 pages each).

**Formula for Macro Slot i:**
- Start Page: `0x03 + (i * 3) // 2`
- Start Offset: `0x80` if `i` is odd, `0x00` if `i` is even.

| Slot | Start Page | Start Offset | End Page | End Offset |
|------|------------|--------------|----------|------------|
| 0 | 0x03 | 0x00 | 0x04 | 0x7F |
| 1 | 0x04 | 0x80 | 0x05 | 0xFF |
| 2 | 0x06 | 0x00 | 0x07 | 0x7F |
| 3 | 0x07 | 0x80 | 0x08 | 0xFF |

### Macro Storage Limit
Because each slot is strictly 384 bytes, and events take ~10 bytes each:
- Max Name Length: ~30 bytes (15 UTF-16 chars)
- Max Events: ~35 characters (350 bytes)
- **Warning:** Macros longer than 35 characters will be truncated by the Windows utility or will overwrite the next macro in memory.


### Special Button Type (0x04) Parameters

Fire Key and Triple Click use type 0x04 with configurable parameters:

```
08 07 00 00 [OFFSET] 04 04 [DELAY_MS] [REPEAT_COUNT] 00 ... [CHK]
```

| Example | Delay | Repeat |
|---------|-------|--------|
| Triple Click | 50ms (0x32) | 3 (0x03) |
| Fire Key | 40ms (0x28) | 3 (0x03) |

Both parameters are adjustable (0-255).

## Media Key Codes (USB HID Consumer Page)

Media keys use consumer page codes, not standard keycodes:

| Code | Function |
|------|----------|
| 0xCD | Play/Pause |
| 0xB5 | Next Track |
| 0xB6 | Previous Track |
| 0xE2 | Mute |
| 0xE9 | Volume Up |
| 0xEA | Volume Down |

**Keyboard region packet for media keys:**
```
08 07 00 [PAGE] [OFFSET] 08 02 82 [MEDIA_CODE] 00 42 [MEDIA_CODE] ...
```

## Macro Event Structure

Macro data is stored on dedicated pages:
- Button flash_index 0 → Page 0x03
- Button flash_index 10 → Page 0x18
- Formula: `page = 0x03 + flash_index`

**Macro Name (Offsets 0x00-0x14):**
- UTF-16LE encoded, ~22 characters max

**Event Data (Offsets 0x1e+):**

Each 11-byte packet contains one key press cycle:
```
0a 00 [DELAY_PREV] [81] [KEYCODE] 00 00 [DELAY_UP] [41] [KEYCODE] 00
```

| Byte | Description |
|------|-------------|
| 0-1 | Header (0x0a 0x00) |
| 2 | Delay from previous event (ms) |
| 3 | 0x81 = Key Down flag |
| 4 | HID Keycode |
| 5-6 | Padding |
| 7 | Delay until key up (ms) |
| 8 | 0x41 = Key Up flag |
| 9 | HID Keycode (repeated) |
| 10 | Padding |

**Terminator (Offset 0x64):**
```
06 00 03 69 00 00 00 00 00 00 00
```

## Known Issues & Quirks

### Timing Requirements

- **Critical:** Must wait 300ms+ between commands
- Fresh HID connection may be needed between button configurations
- Rapid successive writes may be silently ignored

### RAM vs Flash

- Command 0x06 reads from RAM
- Command 0x07 writes to flash
- RAM is NOT automatically updated after flash write
- Device restart may be required to see changes via 0x06

### Reserved Flash Indices

Indices 6-9 appear reserved for system functions (DPI button, etc.). Writing to these may have unexpected effects.

### Wireless vs Wired

Both VID:PID devices (FA07/FA08) accept the same commands, but:
- Windows software typically uses the wireless receiver (FA07)
- Configuration persists in the mouse itself, not the receiver

## Packet Examples

### Set Button 1 to 'A'

```
# Prepare
TX: 08 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 4a
RX: 09 03 00 00 00 01 01 00 00 00 00 00 00 00 00 00 47

# Keyboard region (page=0x01, offset=0x00)
TX: 08 07 00 01 00 08 02 81 04 00 41 04 00 89 00 00 e8
RX: 09 07 00 01 00 08 02 81 04 00 41 04 00 89 00 00 e7

# Mouse region (page=0x00, offset=0x60)
TX: 08 07 00 00 60 04 05 00 00 50 00 00 00 00 00 00 8d
RX: 09 07 00 00 60 04 05 00 00 50 00 00 00 00 00 00 8c
```

### Set Button 12 to 'L'

```
# Keyboard region (page=0x02, offset=0xe0)
TX: 08 07 00 02 e0 08 02 81 0f 00 41 0f 00 73 00 00 [chk]

# Mouse region (page=0x00, offset=0x9c)
TX: 08 07 00 00 9c 04 05 00 00 50 00 00 00 00 00 00 [chk]
```

### Factory Reset

```
TX: 08 09 00 00 00 00 00 00 00 00 00 00 00 00 00 00 43
```

## Tools

- `tools/analyze_capture.py` - Parse USB captures
- `tools/clean_test.py` - Test basic write functionality
- `tools/systematic_probe.py` - Explore protocol systematically

## References

- USB HID Specification 1.11
- HID Usage Tables (for keycodes)
- Windows software USB captures in `usbcap/` directory
