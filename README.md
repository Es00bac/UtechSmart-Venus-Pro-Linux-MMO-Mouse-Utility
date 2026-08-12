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

The repository now contains a complete VCS `PKGBUILD`; it uses Arch's
`python-pyqt6` and `python-hidapi` packages and does not build Python packages
with pip.

### Arch Linux (manual)

Install the Python packages with pacman first. `cython` is included here for
people who also experiment with the PyPI hidapi build; the packaged runtime
does not otherwise need a compiler.

```bash
sudo pacman -S --needed cython python-pyqt6 python-hidapi
git clone https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility.git
cd UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility
./install.sh
```

### Other distributions (manual)

```bash
git clone https://github.com/Es00bac/UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility.git
cd UtechSmart-Venus-Pro-Linux-MMO-Mouse-Utility
python3 -m pip install --user hidapi PyQt6
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
- **Mouse Macro Events:** Add native left, right, and middle press/release events.
- **Battery Tray Icon:** Shows battery level and cable state through Qt's desktop tray API.
- **Battery-color Mouse LED:** Optional minimum-brightness green → yellow →
  orange → red gauge, controlled by the app while it remains in the tray.
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
- **hidapi**
- **PyQt6**

Optional dependencies:

- **python-pyusb** — advanced device management

## Installation notes

### Non-root access with udev

The installer and packages install `packaging/linux/99-venus-pro.rules`. For a
source checkout, install that same reviewed file and reconnect the device:

```bash
sudo install -Dm644 packaging/linux/99-venus-pro.rules /etc/udev/rules.d/99-venus-pro.rules
sudo udevadm control --reload-rules
sudo udevadm trigger --subsystem-match=hidraw
```

The rules cover both the `hidraw` node used by hidapi and the USB device node
used by optional diagnostics. They use desktop-session ACLs (`TAG+="uaccess"`)
with mode `0660`, rather than leaving the mouse world-writable.

### “Mouse detected, but open failed”

The Areson/Compx models expose multiple HID interfaces. Configuration is on
interface 1; interface 0 is the boot mouse and cannot accept these feature
reports. The app now selects the vendor interface explicitly. If it reports an
access error after installation:

1. Unplug and reconnect the mouse or wireless receiver.
2. Confirm that `ls -l /dev/hidraw*` shows an ACL (`+`) for your desktop user.
3. Close the Windows utility, Wine, virtual machines, and USB capture tools
   that may have claimed the device, then click **Reconnect/Refresh**.

For a read-only interface/access diagnostic (and optional battery query), run:

```bash
python3 tools/diagnose_device.py
python3 tools/diagnose_device.py --battery
```

The wired `25a7:fa08`, wireless receiver `25a7:fa07`, and Holtek `04d9:fc55`
variants use different interface selection where needed.

### Battery tray compatibility

The tray icon uses Qt `QSystemTrayIcon`, so it works with KDE Plasma, XFCE,
MATE, and other desktops that expose a StatusNotifier/system tray. GNOME Shell
normally requires its AppIndicator/KStatusNotifier extension. If the desktop
does not expose a tray, the main configuration window still works normally.

The RGB tab and tray menu both expose **Battery-color mouse LED**. This mode
uses the lowest steady-light brightness found in the Windows capture, checks
the battery once per minute, and writes a new color only when the hardware's
10% battery step changes. Closing the window keeps it active in the tray;
quitting the app restores the lighting that was active when the mode was
enabled. The preference is remembered for the next launch.

This is intentionally a user-session background controller rather than a root
daemon: it shares the same hidraw/uaccess permissions as the GUI and can own a
desktop tray icon. On desktops without a tray, the feature continues only
while the main window remains open.

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
- **Battery:** command `0x04` reports 0–10 battery steps and whether the cable is connected; it is a status query, not a write commit.
- **Battery LED:** enable it in the RGB tab or tray menu, then close the window
  to leave the lightweight controller running in the desktop session.
- **Factory reset:** the Advanced tab can restore defaults, but it also wipes custom macros.
- **Read first:** when troubleshooting, start by reading the current device state before staging new writes.

## Known limitations

- This project is based on reverse-engineered device behavior, so unsupported firmware or hardware variants may diverge.
- The repo is focused on the Venus Pro family rather than generic MMO mouse support.
- The `25a7:fa07/fa08` action table contains the 12 side buttons, fire, and the
  three primary mouse buttons, but no entries for its physical top DPI buttons;
  those appear firmware-fixed. The Holtek `04d9:fc55` map does expose DPI Up and
  DPI Down, so those two buttons can be rebound on that variant.
- Mouse movement is not accepted by the vendor macro converter. Native macro
  clicks are supported; relative pointer movement is not currently offered.
- The Areson lighting command is an EEPROM write rather than a known volatile
  LED command. Battery LED mode therefore writes only on a reported 10% step
  change and restores the prior lighting on normal application exit.

## Development

Useful repo entry points if you want to inspect or extend the protocol work:

- `PROTOCOL.md`: current USB HID protocol specification
- `old_stuff/win.md`: archived notes on the Windows utility behavior
- `venus_protocol.py`: core protocol implementation
- `staging_manager.py`: change staging system
- `transaction_controller.py`: HID transaction handling

Run the capture-backed, hardware-safe regression set explicitly:

```bash
python3 -m unittest \
  tests.test_areson_protocol_offline tests.test_battery_led_gui \
  tests.test_protocol tests.test_rgb tests.test_staging \
  tests.test_atomic_controller tests.test_error_recovery
```

Do not treat unrestricted test discovery as hardware-safe. Several older
files under `tests/` and `tools/` are preserved exploratory/replay programs;
some write EEPROM, replay superseded packet guesses, or issue factory reset.
The maintained utility, protocol module, decoder, diagnostic, and explicit
offline suite above are the authoritative paths.

## Release checklist

- Verify the screenshots still match the current UI.
- Confirm the documented USB IDs still match supported hardware paths.
- Re-test button staging, macro upload, DPI writes, polling writes, and factory reset on actual hardware.
- Re-read the udev guidance after any access-model changes.
- Make sure debug artifacts or protocol captures are not accidentally staged.

## Acknowledgments

This utility exists because the mouse is useful on Linux but the vendor stack is not. The project was built through careful inspection of USB protocol behavior to reproduce the practical parts of the Windows configuration flow.
