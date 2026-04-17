# Venus Pro Config (Linux)

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Platform](https://img.shields.io/badge/platform-Linux-1f6feb)
![Python](https://img.shields.io/badge/python-3.8%2B-3776ab)
![Status](https://img.shields.io/badge/status-active%20utility-2d8f6f)

A reverse-engineered Linux configuration utility for the UtechSmart Venus Pro MMO gaming mouse.

It gives Linux users a practical way to manage bindings, macros, DPI profiles, polling rate, and RGB lighting without relying on the vendor's Windows-only software.

## Quickstart

### Arch Linux (AUR)

```bash
yay -S venusprolinux-git
```

### Manual install

```bash
git clone https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility.git
cd UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility
pip install cython hidapi PyQt6
./install.sh
```

Then launch:

```bash
venusprolinux
```

Or run directly from source:

```bash
python3 venus_gui.py
```

## Project status

- Built from reverse-engineered HID protocol work, not vendor documentation.
- Intended for real Linux-side configuration of the Venus Pro family.
- Focused on device configuration, not on replacing the kernel input stack or becoming a full driver daemon.

## Supported device targets

The current repo and udev guidance target these USB IDs:

- `25a7:fa07`
- `25a7:fa08`
- `04d9:fc55`

If your device reports a different ID, verify support before assuming compatibility.

## Features

- **Button Remapping:** Configure all 16 buttons, including the 12-button side panel.
- **Modifier Support:** Bind buttons to combinations such as `Ctrl+Shift+1` and `Alt+F1`.
- **Macro Engine:** Visual macro editor to record and edit events with precise timing.
- **RGB Lighting:** Full control over LED color, brightness, and effects such as Steady, Breathing, Neon, and Off.
- **DPI Profiles:** Configure up to 5 DPI presets with customizable levels.
- **Polling Rate:** Adjust USB polling rate between 125Hz and 1000Hz.
- **Factory Reset:** Restore the device to its original state when troubleshooting or unwinding experiments.

## Screenshots

### Buttons tab

Configure button bindings for all 16 mouse buttons. Supports keyboard keys, mouse actions, macros, media keys, DPI control, and special functions like Fire Key and Triple Click.

![Buttons tab](Buttons.png)

### Macros tab

Visual macro editor with recording functionality. Create key sequences with timing, add manual events, reorder steps, and preview output before binding.

![Macros tab](Macros.png)

### RGB tab

Control LED color, brightness, and effect mode.

- **Off** — disable the LED
- **Steady** — solid color at adjustable brightness
- **Neon** — color cycling effect
- **Breathing** — pulsing fade effect

![RGB tab](RGB.png)

### DPI tab

Configure up to 5 DPI presets across the 100-16,000 DPI range.

![DPI tab](DPI.png)

### Polling tab

Adjust the USB polling rate:

- **125Hz** — lowest CPU usage
- **250Hz**
- **500Hz**
- **1000Hz** — best responsiveness for gaming

### Advanced tab

Diagnostic and recovery tools, including factory reset and debug logging for raw HID communication.

## Requirements

- **Python 3.8+**
- **Cython**
- **hidapi**
- **PyQt6**

Optional dependencies:

- **python-evdev** — software macro playback
- **python-pyusb** — advanced device management

## Installation notes

### Safer non-root access with udev

To access the mouse as a regular user, create a udev rule:

```bash
sudo tee /etc/udev/rules.d/99-venus-pro.rules >/dev/null <<'RULES'
SUBSYSTEM=="usb", ATTR{idVendor}=="25a7", ATTR{idProduct}=="fa07", MODE="0660", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="25a7", ATTR{idProduct}=="fa08", MODE="0660", TAG+="uaccess"
SUBSYSTEM=="usb", ATTR{idVendor}=="04d9", ATTR{idProduct}=="fc55", MODE="0660", TAG+="uaccess"
RULES
sudo udevadm control --reload-rules
sudo udevadm trigger
```

This is preferable to leaving the device world-writable.

## Usage

Typical flow:

1. Click **Read Settings** to load the current device state.
2. Use the **Buttons** tab to choose a button and set an action.
3. Click **Stage Binding** or rely on the auto-stage behavior when switching buttons.
4. Click **Apply All Changes** to write staged bindings to the device.
5. Use the **Macros** tab to record or build a macro, then click **Upload Macro**.
6. Bind the macro to a button with **Bind to Button**.

Practical notes:

- **Wired and wireless:** the app uses the wired connection when present and falls back to the wireless receiver when USB is disconnected.
- **Factory reset:** the Advanced tab can restore defaults, but it also wipes custom macros.
- **Read first:** when troubleshooting, start by reading the current device state before staging new writes.

## Known limitations

- This project is based on reverse-engineered device behavior, so unsupported firmware or hardware variants may diverge.
- The repo is focused on the Venus Pro family rather than generic MMO mouse support.
- Some advanced macro or lighting behaviors may need protocol-level investigation before they can be expanded safely.

## Development

Useful repo entry points if you want to inspect or extend the protocol work:

- `PROTOCOL.md`: current USB HID protocol specification
- `old_stuff/win.md`: archived notes on the Windows utility behavior
- `venus_protocol.py`: core protocol implementation
- `staging_manager.py`: change staging system
- `transaction_controller.py`: HID transaction handling

## Release checklist

- Verify the screenshots still match the current UI.
- Confirm the documented USB IDs still match supported hardware paths.
- Re-test button staging, macro upload, DPI writes, polling writes, and factory reset on actual hardware.
- Re-read the udev guidance after any access-model changes.
- Make sure debug artifacts or protocol captures are not accidentally staged.

## Acknowledgments

This utility exists because the mouse is useful on Linux but the vendor stack is not. The project was built through careful inspection of USB protocol behavior to reproduce the practical parts of the Windows configuration flow.
