# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Venus Pro Config (Linux) is a reverse-engineered configuration utility for the UtechSmart Venus Pro MMO gaming mouse. The project implements the proprietary USB HID protocol to provide Linux users with button remapping, macros, RGB lighting, and DPI controls.

**Hardware:** UtechSmart Venus Pro mouse (VID:PID 0x25A7:0xFA07 wired, 0x25A7:0xFA08 wireless)

## Running the Application

```bash
python3 venus_gui.py
```

**Dependencies:** Python 3.8+, PyQt6, hidapi, cython. Optional: evdev (macro playback), pyusb (magic unlock for macros)

**udev rules for non-root access:**
```bash
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="25a7", ATTRS{idProduct}=="fa07", MODE="0666"' | sudo tee /etc/udev/rules.d/99-venus-pro.rules
echo 'SUBSYSTEM=="usb", ATTRS{idVendor}=="25a7", ATTRS{idProduct}=="fa08", MODE="0666"' | sudo tee -a /etc/udev/rules.d/99-venus-pro.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

## Architecture

### Core Files

- **venus_protocol.py** - USB HID protocol implementation. Contains packet building functions (`build_report`, `build_key_binding`, `build_macro_chunk`, `build_rgb`, `build_dpi`), device enumeration (`list_devices`), and checksum calculation (`calc_checksum` with base 0x55).

- **venus_gui.py** - PyQt6 application with tabbed interface for Buttons, Macros, RGB, Polling, DPI, and Advanced settings. Includes `MacroRunner` QThread for software macro playback via evdev/uinput.

### Protocol Details

All communication uses 17-byte HID feature reports (Report ID 0x08):
- Bytes 0-14: Command ID + payload
- Byte 15: Checksum = `(0x55 - sum(bytes 0-14)) & 0xFF`

**Key Commands:**
- 0x03: Handshake/status
- 0x04: Prepare/commit writes
- 0x07: Write to flash
- 0x08: Read from flash
- 0x09: Factory reset

**Memory Layout:**
- Page 0x00: Main config (buttons at offset 0x60, LED at 0x54, DPI at 0x0C)
- Pages 0x01-0x02: Extended keyboard bindings (32 bytes per button)
- Pages 0x03+: Macro storage

**Magic Unlock:** Pages 0x03+ require special initialization sequence (commands 0x09, 0x4D, 0x01) via PyUSB with root permissions.

### Button Mapping

16 buttons total: 12 side panel + fire key + LMB/MMB/RMB. Each button stored as 4 bytes at page 0x00, offsets 0x60-0x9C.

Action types: 0x00=disabled, 0x01=mouse, 0x02=keyboard, 0x04=fire/triple-click, 0x05=default, 0x06=macro, 0x07=polling toggle, 0x08=RGB toggle

## Testing

Test scripts in root directory (`test_*.py`) validate specific protocol features. Run individual tests directly:
```bash
python3 test_checksum_necessity.py
```

## Key Development Notes

- **Wired mode required** for reliable configuration writes to flash
- Protocol derived from USB capture analysis (32+ captures in `usbcap/`)
- Memory dumps in `dumps/` used to verify flash memory layout
- See `PROTOCOL.md` for the current USB HID protocol specification
