# UtechSmart Venus Mouse - Key Binding Protocol Documentation

This document explains the reverse-engineered protocol for setting keyboard bindings on the UtechSmart Venus Wireless Gaming Mouse. These bindings work in **wired mode only** - wireless mode requires further investigation.

## Device Information

| Mode | VID:PID | Product String |
|------|---------|----------------|
| Wired | 25A7:FA08 | 2.4G Dual Mode Mouse |
| Wireless | 25A7:FA07 | 2.4G Wireless Receiver |

Use HID interface 1 for configuration commands.

## Protocol Overview

The mouse uses HID feature reports for configuration:
- **Report ID 8**: Send commands (16 bytes payload + 1 byte checksum = 17 bytes total)
- **Report ID 9**: Receive responses
- **Checksum**: Sum of all 17 bytes must equal `0x55`

## Command Format

```
[Report_ID, CMD, ...params...] + padding to 16 bytes + checksum
```

### Key Commands

| Command | Format | Description |
|---------|--------|-------------|
| 0x03 | `[0x03]` | Prepare/unlock flash for writing (required before 0x07) |
| 0x07 | `[0x07, 0x00, page, offset, data...]` | Write to flash memory |
| 0x09 | `[0x09]` | Factory reset to defaults |

## Flash Memory Layout

### Critical Discovery: Reserved Indices

**Flash indices 6-9 are reserved** (likely for DPI buttons). The button-to-flash-index mapping is NOT linear:

```python
BUTTON_TO_FLASH_INDEX = {
    1: 0,   2: 1,   3: 2,   4: 3,   5: 4,   6: 5,    # Linear
    7: 8,   8: 9,                                      # Skip indices 6-7
    9: 12,  10: 13, 11: 14, 12: 15,                   # Skip indices 10-11
    13: 11, 14: 10,                                    # Buttons 13-14 use 11, 10
    15: 16, 16: 17,                                    # Continue from 16
}
```

### Memory Regions

Each button binding requires writes to TWO regions:

1. **Mouse Region** (page=0x00): Tells the mouse what type of binding
   - Offset: `0x60 + (flash_index * 4)`

2. **Keyboard Region** (page=0x01+): Contains the actual key data
   - Page: `0x01 + (flash_index // 8)`
   - Offset: `(flash_index % 8) * 0x20`

### Address Examples

| Button | Flash Index | Mouse Offset | Kbd Page | Kbd Offset |
|--------|-------------|--------------|----------|------------|
| 1 | 0 | 0x60 | 0x01 | 0x00 |
| 2 | 1 | 0x64 | 0x01 | 0x20 |
| 6 | 5 | 0x74 | 0x01 | 0xA0 |
| 7 | 8 | 0x80 | 0x02 | 0x00 |
| 8 | 9 | 0x84 | 0x02 | 0x20 |
| 12 | 15 | 0x9C | 0x02 | 0xE0 |
| 13 | 11 | 0x8C | 0x02 | 0x60 |

## Writing a Keyboard Binding

To bind a button to a keyboard key:

### Step 1: Send Prepare Command (0x03)

```
08 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 [checksum]
```

### Step 2: Write Keyboard Region

Format:
```
08 07 00 [kbd_page] [kbd_offset] 08 02 81 [keycode] [modifier] 41 [keycode] 00 [mystery] 00 00 [checksum]
```

**Mystery Byte Calculation:**
```python
mystery_byte = (0x91 - (keycode * 2)) & 0xFF
```

Example for 'A' key (keycode=0x04):
- mystery_byte = 0x91 - (0x04 * 2) = 0x91 - 0x08 = 0x89

### Step 3: Write Mouse Region

Format:
```
08 07 00 00 [mouse_offset] 04 05 00 00 50 00 00 00 00 00 00 [checksum]
```

The `04 05` indicates this is a keyboard-type binding.

## Complete Example: Bind Button 1 to 'A'

Button 1 → Flash index 0

**Addresses:**
- Mouse: page=0x00, offset=0x60
- Keyboard: page=0x01, offset=0x00

**Commands:**

```
# 1. Prepare
08 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 4a

# 2. Write keyboard data (page=0x01, offset=0x00, keycode=0x04, mystery=0x89)
08 07 00 01 00 08 02 81 04 00 41 04 00 89 00 00 e8

# 3. Write mouse region (page=0x00, offset=0x60)
08 07 00 00 60 04 05 00 00 50 00 00 00 00 00 00 8d
```

## HID Key Codes

Common HID Usage IDs for keyboard keys:

| Key | Code | Key | Code |
|-----|------|-----|------|
| A | 0x04 | N | 0x11 |
| B | 0x05 | O | 0x12 |
| C | 0x06 | P | 0x13 |
| D | 0x07 | Q | 0x14 |
| E | 0x08 | R | 0x15 |
| F | 0x09 | S | 0x16 |
| G | 0x0A | T | 0x17 |
| H | 0x0B | U | 0x18 |
| I | 0x0C | V | 0x19 |
| J | 0x0D | W | 0x1A |
| K | 0x0E | X | 0x1B |
| L | 0x0F | Y | 0x1C |
| M | 0x10 | Z | 0x1D |

## Python Implementation

```python
import hid
import time

VENDOR_ID = 0x25A7
PRODUCT_ID_WIRED = 0xFA08
REPORT_ID = 0x08

BUTTON_TO_FLASH_INDEX = {
    1: 0, 2: 1, 3: 2, 4: 3, 5: 4, 6: 5,
    7: 8, 8: 9,
    9: 12, 10: 13, 11: 14, 12: 15,
    13: 11, 14: 10,
    15: 16, 16: 17,
}

def calc_checksum(data):
    """Sum of all 17 bytes must equal 0x55"""
    return (0x55 - sum(data[:16])) & 0xFF

def send_command(dev, cmd):
    """Send command with proper padding and checksum"""
    full_cmd = [REPORT_ID] + list(cmd)
    full_cmd += [0x00] * (16 - len(full_cmd))  # Pad to 16 bytes
    full_cmd.append(calc_checksum(full_cmd))   # Add checksum
    dev.send_feature_report(bytes(full_cmd))
    time.sleep(0.02)

def bind_button_to_key(dev, button_index, keycode, modifier=0):
    """Bind a button to a keyboard key"""
    flash_index = BUTTON_TO_FLASH_INDEX.get(button_index, button_index - 1)

    # Calculate addresses
    mouse_offset = 0x60 + (flash_index * 4)
    kbd_page = 0x01 + (flash_index // 8)
    kbd_offset = (flash_index % 8) * 0x20
    mystery_byte = (0x91 - (keycode * 2)) & 0xFF

    # 1. Prepare
    send_command(dev, [0x03])
    time.sleep(0.05)

    # 2. Write keyboard region
    kbd_data = [0x07, 0x00, kbd_page, kbd_offset,
                0x08, 0x02, 0x81, keycode, modifier, 0x41, keycode, 0x00, mystery_byte, 0x00, 0x00]
    send_command(dev, kbd_data)
    time.sleep(0.05)

    # 3. Write mouse region
    mouse_data = [0x07, 0x00, 0x00, mouse_offset,
                  0x04, 0x05, 0x00, 0x00, 0x50, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]
    send_command(dev, mouse_data)

# Usage example
def main():
    # Find and open device
    dev = hid.device()
    for d in hid.enumerate(VENDOR_ID, PRODUCT_ID_WIRED):
        if d['interface_number'] == 1:
            dev.open_path(d['path'])
            break

    dev.set_nonblocking(True)

    # Bind button 1 to 'A' (keycode 0x04)
    bind_button_to_key(dev, button_index=1, keycode=0x04)

    dev.close()

if __name__ == "__main__":
    main()
```

## Known Limitations

1. **Wireless Mode**: Bindings do NOT persist in wireless mode. The wireless receiver (FA07) accepts commands but doesn't store them. Further reverse engineering needed.

2. **Reserved Indices**: Indices 6-7 and possibly 8-9 appear reserved for DPI/system buttons.

3. **Button 13-14 Mapping**: These buttons use indices 11 and 10 respectively (reversed order from what you'd expect).

## Verification

The flash writes are persistent - they survive power cycles and reconnects in wired mode. To verify bindings work:

1. Write bindings using the protocol above
2. Unplug and replug the USB cable
3. Test button presses - they should output the assigned keys

## Factory Reset

To reset all bindings to defaults:

```
08 09 00 00 00 00 00 00 00 00 00 00 00 00 00 00 44
```

This resets BOTH wired and wireless profiles.

## Files Reference

- `/home/cabewse/utechsmart-linux/utechsmart/device.py` - Main device driver with `set_button_binding_flash()` method
- `/home/cabewse/utechsmart-linux/utechsmart/constants.py` - Protocol constants and enums
- `/home/cabewse/utechsmart-linux/CLAUDE.md` - Project documentation
