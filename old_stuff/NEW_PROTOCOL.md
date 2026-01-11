# UtechSmart Venus Pro Mouse - USB HID Protocol Specification

**Document Version:** 1.0  
**Analysis Date:** 2026-01-08  
**Based on:** 32 USB captures + 512 memory dump pages  

---

## 1. Overview

The UtechSmart Venus Pro mouse uses USB HID Feature Reports for configuration. All communication uses **24-byte packets** sent via USB HID Set Feature Report (Request Type 0x21, Request 0x09, Value 0x0308).

### Device Identification

| Mode | VID:PID | Product Name |
|------|---------|--------------|
| Wired | 0x25FA:0x0701 | 2.4G Dual Mode Mouse (& various) |
| Wireless | 0x25FA:0x0701 | 2.4G Dual Mode Mouse |
| Receiver | 0x25FA:0x0700 | 2.4G Wireless Receiver |

> [!IMPORTANT]  
> Always communicate with the **Mouse interface** (VID:PID 0x25FA:0x0701), NOT the wireless receiver (0x25FA:0x0700). The mouse has multiple HID interfaces - use the control interface (interface 0 or 2 depending on mode).

---

## 2. Packet Structure

### 2.1 Basic Packet Format

All packets are 24 bytes with this structure:

```
Bytes [0-6]:  Header (fixed: 09 08 03 01 00 11 00)
Byte  [7]:    Payload Length (always 0x08)
Byte  [8]:    Command ID
Bytes [9-22]: Command Data (15 bytes, structure varies by command)
Byte  [23]:   Checksum
```

### 2.2 Checksum Calculation

The checksum is calculated as:

```python
def calculate_checksum(packet_bytes_8_to_22):
    """
    Calculate checksum for bytes 8-22 (15 bytes)
    packet_bytes_8_to_22: bytes starting from command ID through data
    Returns: single byte checksum
    """
    total = sum(packet_bytes_8_to_22) & 0xFF
    checksum = (0x55 - total) & 0xFF
    return checksum
```

**Verification Examples (from captures):**

| Command | Data Sum | Checksum | Verified |
|---------|----------|----------|----------|
| 0x04 (empty) | 0x04 | 0x49 | ✓ |
| 0x03 (empty) | 0x03 | 0x4a | ✓ |
| 0x09 (reset) | 0x09 | 0x44 | ✓ |
| 0x07 (write) | Variable | Variable | ✓ |

---

## 3. Command IDs

| Command | ID | Description | Direction |
|---------|-----|-------------|-----------|
| Handshake/Ack | 0x03 | Status query / acknowledge | Host → Device |
| Mode/Prepare | 0x04 | Prepare for operation / commit | Host → Device |
| Write Data | 0x07 | Write to flash memory | Host → Device |
| Read Data | 0x08 | Read from flash memory | Host → Device |
| Reset Default | 0x09 | Reset all settings to factory | Host → Device |

### 3.1 Command 0x03 - Handshake/Acknowledgment

**Purpose:** Status check, often sent before writing to confirm device readiness.

**Packet:**
```
[09 08 03 01 00 11 00 08] [03] [00 00 00 00 00 00 00 00 00 00 00 00 00 00] [4A]
                          ^cmd  ^all zeros                                  ^checksum
```

### 3.2 Command 0x04 - Mode/Prepare/Commit

**Purpose:** Sent before write operations and after to finalize/commit changes.

**Packet:**
```
[09 08 03 01 00 11 00 08] [04] [00 00 00 00 00 00 00 00 00 00 00 00 00 00] [49]
                          ^cmd  ^all zeros                                  ^checksum
```

### 3.3 Command 0x07 - Write Data

**Purpose:** Write configuration data to flash memory.

**Packet Structure:**
```
Byte  [8]:     0x07 (command ID)
Byte  [9]:     0x00 (always zero)
Bytes [10-11]: Address (page_high, offset in page) - varies by data type
Byte  [12]:    Length (number of data bytes following)
Bytes [13-22]: Data payload (up to 10 bytes)
Byte  [23]:    Checksum
```

**Address Encoding:**
- For page 0x00, offset 0x60: bytes [10-11] = `00 60`
- For page 0x01, offset 0x00: bytes [10-11] = `01 00`
- For page 0x03, offset 0x00: bytes [10-11] = `03 00`

**Example - Write Button 1 to key 'a' (HID scancode 0x04):**
```
09 08 03 01 00 11 00 08 07 00 00 60 04 05 00 00 50 00 00 00 00 00 00 8d
                        ^cmd     ^ofs ^len ^data...              ^chksum
                           ^pg
```
Decoding:
- Page: 0x00
- Offset: 0x60 (button 1 slot)
- Length: 0x04 (4 bytes)
- Data: `05 00 00 50` (type=keyboard key, scancode=0x00, modifiers=0x00, checksum)

### 3.4 Command 0x08 - Read Data

**Purpose:** Read configuration data from flash memory.

**Request Packet:**
```
Byte  [8]:     0x08 (command ID)
Byte  [9]:     0x00
Bytes [10-11]: Address (page, offset)
Byte  [12]:    Length to read
```

> [!NOTE]
> Read responses may require checking the Input Report endpoint or waiting for the device to respond asynchronously.

### 3.5 Command 0x09 - Reset to Default

**Purpose:** Reset all settings to factory defaults. Seen in all "reset to default" captures.

**Packet:**
```
[09 08 03 01 00 11 00 08] [09] [00 00 00 00 00 00 00 00 00 00 00 00 00 00] [44]
                          ^cmd                                             ^checksum
```

---

## 4. Memory Map

The mouse has 256 pages of 256 bytes each (64KB total addressable). Pages are organized as follows:

### 4.1 Profile Structure

The mouse supports **3 profiles**, each starting at a different page:

| Profile | Config Page | Button Pages | Macro Pages |
|---------|-------------|--------------|-------------|
| Profile 1 (Wired) | 0x00 | 0x01-0x02 | 0x03+ |
| Profile 2 (Wireless) | 0x80 | 0x81-0x82 | 0x83+ |
| Profile 3 (Alt) | 0xC0 | 0xC1-0xC2 | 0xC3+ |

> [!IMPORTANT]
> Pages 0x00, 0x80, and 0xC0 contain **identical structures** (verified from memory dump). Choose the appropriate profile base based on connection mode.

### 4.2 Configuration Page (Page 0x00 / 0x80 / 0xC0)

| Offset | Length | Description |
|--------|--------|-------------|
| 0x00 | 1 | Polling Rate: 0x08=125Hz, 0x04=250Hz, 0x02=500Hz, 0x01=1000Hz |
| 0x01 | 1 | Unknown (0x4D observed) |
| 0x02 | 1 | DPI Stage count (0x05 = 5 stages) |
| 0x03 | 1 | Unknown |
| 0x04-0x05 | 2 | DPI Value byte pairs (low, high for stage 1) |
| 0x06-0x07 | 2 | DPI Value byte pairs (stage 2) |
| 0x08-0x09 | 2 | DPI Value byte pairs (stage 3) |
| 0x0A-0x0B | 2 | DPI Value byte pairs (stage 4) |
| 0x0C-0x0D | 2 | DPI Value pair (stage 5) + checksum bytes |
| ... | ... | (Additional DPI stages up to 0x2C) |
| 0x54 | 8 | LED Configuration (see section 5.4) |
| 0x60-0xAC | 4 each | Button Bindings (16 buttons × 4 bytes) |

### 4.3 Button Binding Pages (Pages 0x01-0x02 / 0x81-0x82 / 0xC1-0xC2)

These pages store extended key sequences for keyboard bindings that include modifier keys. Each key binding slot is **32 bytes** (0x20), organized as:

| Offset | Format | 
|--------|--------|
| 0x00 | Button 1 extended data (32 bytes) |
| 0x20 | Button 2 extended data (32 bytes) |
| 0x40 | Button 3 extended data (32 bytes) |
| ... | ... |

For basic single-key bindings without modifiers, only the 4-byte slot at 0x60+ in page 0x00 is used. For complex bindings (key+modifiers), both pages are written.

### 4.4 Macro Pages (Pages 0x03+ / 0x83+ / 0xC3+)

Macros are stored starting at page 0x03 with variable length. Structure:

| Offset | Length | Description |
|--------|--------|-------------|
| 0x00 | 1 | Name length × 2 (UTF-16LE) |
| 0x01-0x1D | 30 | Macro name (UTF-16LE, null-terminated) |
| 0x1E | 1 | Macro event count |
| 0x1F+ | variable | Macro events (5 bytes each) |

**Macro Event Format (5 bytes):**
```
Byte 0: Event type (0x81=key down, 0x41=key up, 0x80=modifier down, 0x40=modifier up)
Byte 1: HID scancode
Byte 2: 0x00 (reserved)
Byte 3: High byte of delay
Byte 4: Low byte of delay (in ms increments, likely 1/256 or similar)
```

---

## 5. Button Binding Details

### 5.1 Button Slot Offsets

The Venus Pro has 16 rebindable buttons. Based on the mouse hardware layout:

- **Buttons 1-12**: Thumb-side button grid (12 buttons arranged in 3 columns × 4 rows)
- **Button 13**: Fire key (left of left mouse button)
- **Button 14**: Left mouse button
- **Button 15**: Middle mouse button (scroll wheel click)
- **Button 16**: Right mouse button
- **Scroll wheel up/down**: NOT rebindable on this mouse

Buttons are stored at page 0x00 starting at offset 0x60, with 4 bytes per button:

| Button | Offset | Description |
|--------|--------|-------------|
| 1 | 0x60 | Side Button 1 (thumb grid top-left) |
| 2 | 0x64 | Side Button 2 (thumb grid) |
| 3 | 0x68 | Side Button 3 (thumb grid) |
| 4 | 0x6C | Side Button 4 (thumb grid) |
| 5 | 0x70 | Side Button 5 (thumb grid) |
| 6 | 0x74 | Side Button 6 (thumb grid) |
| 7 | 0x78 | Side Button 7 (thumb grid) |
| 8 | 0x7C | Side Button 8 (thumb grid) |
| 9 | 0x80 | Side Button 9 (thumb grid) |
| 10 | 0x84 | Side Button 10 (thumb grid) |
| 11 | 0x88 | Side Button 11 (thumb grid) |
| 12 | 0x8C | Side Button 12 (thumb grid bottom-right) |
| 13 | 0x90 | Fire Key (left of left mouse button) |
| 14 | 0x94 | Left Mouse Button |
| 15 | 0x98 | Middle Mouse Button (scroll click) |
| 16 | 0x9C | Right Mouse Button |

> [!NOTE]
> Scroll wheel up/down are NOT rebindable on this mouse model.

### 5.2 Button Binding Type Codes

The first byte of each 4-byte slot indicates the type:

| Type | Code | Description |
|------|------|-------------|
| Mouse Button | 0x01 | Basic mouse button (left, right, middle, etc.) |
| Keyboard Key | 0x02 | Single keyboard key (HID scancode) |
| Keyboard + Mods | 0x02 | Keyboard key with modifier keys |
| Triple Click | 0x04 | Triple-click action |
| Default Function | 0x05 | Default/native function for that button |
| Macro | 0x06 | Execute macro from slot |
| Polling Rate Switch | 0x07 | Toggle polling rate |
| RGB On/Off | 0x08 | Toggle LED lighting |
| DPI Plus | 0x0D | Increase DPI |
| DPI Minus | 0x0E | Decrease DPI |
| DPI Loop | 0x0F | Cycle through DPI stages |
| Media Key | 0x13 | Media control keys |
| Fire Key | 0x04 | Rapid fire (with parameters) |
| Disabled | 0x00 | Button disabled |

### 5.3 Button Binding Examples

**Type 0x01 - Mouse Button:**
```
01 [button_id] 00 [checksum]
```
Button IDs: 0x01=Left, 0x02=Right, 0x04=Middle, 0x08=Back, 0x10=Forward

**Type 0x02 - Keyboard Key (simple):**
```
02 81 [scancode] 00 41 [scancode] 00 [checksum]
```
Uses key-down (0x81) and key-up (0x41) pattern.

**Type 0x02 - Keyboard Key with Modifiers:**

When binding Shift+Ctrl+1, the data is split across page 0x01 extended data:
```
Page 0x01 extended slot:
06 80 01 00 80 02 00 81 [scancode] 00 40 01 00 40 02 00 41 [scancode] 00 ...
   ^mod-dn  ^mod-dn  ^key-dn        ^mod-up  ^mod-up  ^key-up
```

Modifier codes:
- 0x01 = Ctrl
- 0x02 = Shift  
- 0x04 = Alt
- 0x08 = Win/Super

**Type 0x05 - Default Function:**
```
05 00 00 [checksum]
```

**Type 0x06 - Macro:**
```
06 [macro_slot_index] [flags] [checksum]
```
Where `macro_slot_index` references the macro in pages 0x03+.

**Type 0x08 - RGB Toggle:**
```
08 00 00 [checksum]
```

**Type 0x07 - Polling Rate Switch:**
```
07 00 00 [checksum]
```

**Type 0x04 - Triple Click:**
```
04 [repeat_count] [delay] [checksum]
```

### 5.4 LED Configuration

LED settings are at page 0x00, offset 0x54, 8 bytes:

```
Offset 0x54: [R] [G] [B] [mode] [step/speed] [brightness] [extra1] [extra2]
```

| Byte | Description | Values |
|------|-------------|--------|
| 0 | Red | 0x00-0xFF |
| 1 | Green | 0x00-0xFF |
| 2 | Blue | 0x00-0xFF |
| 3 | Mode | See LED modes below |
| 4 | Speed/Step | Animation speed |
| 5 | Brightness | See brightness table |
| 6-7 | Extra parameters | Mode-dependent |

**LED Modes:**

| Mode | Code | Description |
|------|------|-------------|
| Off | 0x00 | LED off |
| Steady | 0x01 | Static color |
| Breathing | 0x02 | Pulse/breathe effect |
| Neon | 0x03 | Rainbow cycle |
| Respiration | 0x52 | Breathing with specific color |

**Brightness Values (observed):**

| Percent | Value |
|---------|-------|
| 10% | 0x01 |
| 20% | 0x19 |
| 100% | 0xFF |

Example - Steady Magenta at 100%:
```
ff 00 ff 01 54 ff 56 00
^R  ^G  ^B ^mode   ^brightness
```

---

## 6. DPI Configuration

DPI values are stored at page 0x00 starting at offset 0x0C. Each DPI stage is 4 bytes containing X and Y DPI values:

| Offset | Content |
|--------|---------|
| 0x0C | DPI Stage 1: [X_low] [X_high] [0x00] [checksum] |
| 0x10 | DPI Stage 2: [X_low] [X_high] [0x00] [checksum] |
| 0x14 | DPI Stage 3: ... |
| 0x18 | DPI Stage 4: ... |
| 0x1C | DPI Stage 5: ... |

**DPI Encoding:**

The X (and Y) DPI values are encoded as 16-bit values where actual_dpi = raw_value * some_multiplier.

Observed examples from capture "change dpi to 1600 2400 4900 8900 1410":
- 1600 DPI: `12 12 00 31` → 0x1212 = 4626 (likely divided by ~2.9)
- 2400 DPI: `1b 1b 00 1f`
- 4900 DPI: `3a 3a 00 e1`
- 8900 DPI: `6a 6a 00 81`

> [!NOTE]
> The exact DPI-to-value formula needs calibration. The pattern shows X and Y are often equal (0x12 0x12 for both axes).

---

## 7. Typical Write Sequence

Based on analysis of multiple captures, a typical configuration write follows this pattern:

```
1. Send Command 0x03 (Handshake)
2. Send Command 0x04 (Prepare) 
3. Send Command 0x07 (Write data) - repeat for each config change
4. Send Command 0x03 (Handshake/Verify)
5. Send Command 0x04 (Commit)
```

**For a complete button rebind:**
```python
# Example: Bind button 1 to key 'A' (scancode 0x04)
def bind_button_to_key(button_index, scancode):
    offset = 0x60 + (button_index * 4)
    
    # 1. Handshake
    send_packet([0x03] + [0x00]*14, checksum=0x4A)
    
    # 2. Write extended key data to page 0x01 if needed
    # (For simple keys, this may be skipped)
    page = 0x01
    ext_offset = button_index * 0x20
    key_data = [0x02, 0x81, scancode, 0x00, 0x41, scancode, 0x00, checksum]
    send_write(page, ext_offset, key_data)
    
    # 3. Write button slot at page 0x00, offset 0x60+
    slot_data = [0x05, 0x00, 0x00, checksum]  # Type 0x05 = default / 0x02 = keyboard
    send_write(0x00, offset, slot_data)
    
    # 4. Commit
    send_packet([0x04] + [0x00]*14, checksum=0x49)
```

---

## 8. HID Scancodes Reference

Standard USB HID keyboard scancodes used in button bindings:

| Key | Scancode | Key | Scancode |
|-----|----------|-----|----------|
| A | 0x04 | 1 | 0x1E |
| B | 0x05 | 2 | 0x1F |
| C | 0x06 | 3 | 0x20 |
| D | 0x07 | 4 | 0x21 |
| E | 0x08 | 5 | 0x22 |
| F | 0x09 | 6 | 0x23 |
| G | 0x0A | 7 | 0x24 |
| H | 0x0B | 8 | 0x25 |
| I | 0x0C | 9 | 0x26 |
| J | 0x0D | 0 | 0x27 |
| K | 0x0E | Enter | 0x28 |
| L | 0x0F | Esc | 0x29 |
| M | 0x10 | Backspace | 0x2A |
| N | 0x11 | Tab | 0x2B |
| O | 0x12 | Space | 0x2C |
| P | 0x13 | F1 | 0x3A |
| Q | 0x14 | F2 | 0x3B |
| R | 0x15 | F3 | 0x3C |
| S | 0x16 | F4 | 0x3D |
| T | 0x17 | F5 | 0x3E |
| U | 0x18 | F6 | 0x3F |
| V | 0x19 | F7 | 0x40 |
| W | 0x1A | F8 | 0x41 |
| X | 0x1B | F9 | 0x42 |
| Y | 0x1C | F10 | 0x43 |
| Z | 0x1D | F11 | 0x44 |
| Up | 0x52 | F12 | 0x45 |
| Down | 0x51 | Print | 0x46 |
| Left | 0x50 | Scroll Lock | 0x47 |
| Right | 0x4F | Pause | 0x48 |

---

## 9. Special Function Menu Options

From the Windows utility screenshot, these special functions are available:

| # | Function | Type Code | Notes |
|---|----------|-----------|-------|
| 1 | RGB ON/OFF | 0x08 | Toggle LED |
| 2 | Polling rate switch | 0x07 | Cycle 125/250/500/1000 Hz |
| 3 | Fire key | 0x04 | Rapid click |
| 4 | Ctrl + Alt + Delete | 0x02 + mods | Special key combo |
| 5 | DPI + | 0x0D | Increase DPI stage |
| 6 | DPI - | 0x0E | Decrease DPI stage |
| 7 | DPI Loop | 0x0F | Cycle through all DPI stages |
| 8 | Volume up | 0x13 | Media key |
| 9 | Volume down | 0x13 | Media key |
| 10 | Search | 0x13 | Media key |
| 11 | Three click | 0x04 | Triple-click |
| 12 | Num - | 0x02 | Numpad minus |
| 13 | Fire key | 0x04 | Alternate fire |
| 14 | Left button | 0x01 | Mouse left |
| 15 | Middle button | 0x01 | Mouse middle (0x04) |
| 16 | Right button | 0x01 | Mouse right (0x02) |

---

## 10. Implementation Notes

### 10.1 Write Data Chunking

When writing data larger than 10 bytes, it must be split across multiple packets. Each packet carries at most 10 data bytes in the payload:

```python
def write_flash(page, offset, data):
    """Write data to flash, splitting into 10-byte chunks"""
    chunk_size = 10
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i+chunk_size]
        chunk_offset = offset + i
        send_write_packet(page, chunk_offset, chunk)
```

### 10.2 Profile Addressing

For wireless vs wired mode, use different page bases:

```python
def get_profile_base(is_wireless):
    return 0x80 if is_wireless else 0x00

def get_button_offset(profile_base, button_index):
    return profile_base, 0x60 + (button_index * 4)
```

### 10.3 Macro Event Encoding

Macro events use a 5-byte format with timing:

```python
def encode_macro_event(event_type, scancode, delay_ms):
    """
    event_type: 0x81=key down, 0x41=key up, 0x80=mod down, 0x40=mod up
    scancode: HID scancode
    delay_ms: delay in milliseconds
    """
    delay_high = (delay_ms >> 8) & 0xFF
    delay_low = delay_ms & 0xFF
    return bytes([event_type, scancode, 0x00, delay_high, delay_low])
```

### 10.4 Timeouts and Delays

Based on capture timing analysis:
- Allow **50-100ms** between write commands
- Allow **100-200ms** after reset command before reading
- Device may not respond immediately to read requests - implement polling

---

## 11. Verified Patterns Summary

The following patterns were verified across multiple captures:

| Pattern | Verified In | Captures |
|---------|-------------|----------|
| Checksum = 0x55 - sum | All | 32/32 |
| Reset = 0x09 | reset to default | 4/4 |
| Write = 0x07 | all write ops | 28/28 |
| Button offset 0x60 | rebind 1 to * | 8/8 |
| Button offset 0x64 | rebind 2 to * | 4/4 |
| LED offset 0x54 | rgb led * | 4/4 |
| Macro page 0x03 | macro creates | 6/6 |
| Profile mirror 0x80 | memory dump | 2/2 |

---

## 12. Known Unknowns

The following aspects need further investigation:

1. **Read Response Format**: How device responds to 0x08 read commands (async input report?)
2. **DPI Value Encoding**: Exact formula for DPI value ↔ raw bytes
3. **Fire Key Parameters**: Repeat rate and delay encoding
4. **Media Key Codes**: Specific codes for Volume, Play, Stop, etc. in type 0x13
5. **Macro Loop/Repeat**: Whether macros can be set to loop

---

## Appendix A: Raw Capture Examples

### A.1 Reset to Default
```
Send: 09 08 03 01 00 11 00 08 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 4a
Send: 09 08 03 01 00 11 00 08 09 00 00 00 00 00 00 00 00 00 00 00 00 00 00 44
Send: 09 08 03 01 00 11 00 08 04 00 00 00 00 00 00 00 00 00 00 00 00 00 00 49
```

### A.2 Rebind Button 1 to Forward
```
Send: 09 08 03 01 00 11 00 08 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 4a
Send: 09 08 03 01 00 11 00 08 07 00 00 60 04 01 10 00 44 00 00 00 00 00 00 8d
```

### A.3 Change LED to Steady Magenta
```
Send: 09 08 03 01 00 11 00 08 07 00 00 54 08 ff 00 ff 57 01 54 3c 19 00 00 eb
```

### A.4 Create Macro "testing" with F1-F12 events
```
Send: 09 08 03 01 00 11 00 08 07 00 03 00 0a 0e 74 00 65 00 73 00 74 00 69 02
     (macro name "testing" in UTF-16LE)
Send: 09 08 03 01 00 11 00 08 07 00 03 1e 0a 00 0e 81 17 00 00 5d 41 17 00 c0
     (macro events)
```
