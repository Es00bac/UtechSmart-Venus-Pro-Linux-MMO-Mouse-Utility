# UtechSmart Venus mouse protocols

This document separates two unrelated protocols that are sold under similar
Venus names. It is derived from the repository's USBPcap traces, EEPROM dumps,
live Linux USB descriptors, and decompilation of the bundled Windows utility.

Evidence labels used below:

- **Capture** — directly present in USB traffic.
- **Binary** — implemented by the vendor utility.
- **Descriptor** — declared by the live USB/HID descriptor.
- **Live** — reproduced with a read-only query against the connected device.
- **Inference** — consistent with the evidence, but its user-facing meaning is
  not completely proved.

## Protocol families

| USB ID | Controller/family | Config interface | Protocol |
|---|---|---:|---|
| `25a7:fa07` | Areson/Compx wireless receiver | 1 | 17-byte reports described below |
| `25a7:fa08` | Areson/Compx wired connection | 1 | Same Areson protocol |
| `04d9:fc55` | Holtek wired Venus MMO | 2 | Separate `F1/F2/F3/F5` protocol |

Do not send Areson packets to the Holtek device. The Holtek implementation and
its five-profile memory map are documented in `holtek_protocol.py`.

## Areson transport (`25a7:fa07` and `25a7:fa08`)

The device has separate boot-mouse and keyboard/vendor HID interfaces. The
configuration channel is interface 1. On the live `fa07` descriptor:

- feature report `0x08` is 17 bytes and belongs to vendor usage page `0xff02`;
- interrupt-IN report `0x09` is 17 bytes and belongs to vendor usage page
  `0xff01`;
- responses arrive on endpoint `0x82`.

This is a request/response channel, not one bidirectional report. Requests are
sent with HID `SET_REPORT(Feature)` (`wValue=0x0308`, `wIndex=1`) and responses
arrive asynchronously as interrupt report `0x09`. **Descriptor, Capture**

### Packet format

Every request and response is exactly 17 bytes:

```text
00     report ID: 08 request, 09 response
01     command
02     reserved (00 in every captured protocol packet)
03-04  16-bit address, big-endian (commands 07/08)
05     data length
06-15  up to 10 data bytes, zero-padded on requests
16     checksum
```

The checksum invariant is:

```python
sum(packet) & 0xff == 0x55
checksum = (0x55 - sum(packet[0:16])) & 0xff
```

The old documentation called bytes 3 and 4 “profile page” and “offset.” That
representation can construct the bytes, but the vendor binary treats them as
one 16-bit EEPROM address. The Areson model configuration exposes one hardware
profile (`ShowProSw=0`); adding `0x40/0x80/0xc0` to page numbers writes unrelated
high EEPROM regions. **Capture, Binary**

### Commands

| Command | Request | Response and meaning | Evidence |
|---:|---|---|---|
| `01` | length 4, random challenge | length 4, transformed challenge | Capture, Binary |
| `02` | length 1, data `01` | echoes `01`; enables/announces driver state | Capture; semantic name is Inference |
| `03` | empty | length 1, data `01`; ready/begin-operation handshake | Capture, Binary |
| `04` | empty | length 2: battery step, cable flag | Capture, Binary |
| `07` | address, length, data | acknowledges/echoes the write | Capture, Binary |
| `08` | address and length | returns length and EEPROM data | Capture, Binary |
| `09` | empty | factory reset; erases settings and macros | Capture, Binary |

There is no command `0x4d` in any supplied capture. It was an artifact of the
old implementation. Likewise, command `0x04` is not prepare/commit. EEPROM
writes persist after their `0x07` acknowledgement; the Windows utility does not
send a commit after each write group. **Capture, Binary**

#### Challenge response (`01`)

For challenge bytes `a,b,c,d`, the expected response is:

```text
r0 = a + b + 5
r1 = 2*b + c
r2 = 3*c + d
r3 = 4*d + a
```

All operations are modulo 256. Five independent captured challenge pairs match
this formula. The old code replayed one pair and mislabeled it an unlock. The
vendor utility generates each challenge byte in the range 1–100 and verifies
the response. **Capture, Binary**

#### Vendor startup sequence

The Windows utility performs this non-destructive sequence:

1. `03` ready
2. `01` random challenge
3. `08` read two bytes at `0x0004`
4. `02` with data `01`
5. configuration reads
6. `04` status query

Writing normally begins with `03`, followed by one or more `07` writes. Factory
reset (`09`) is never part of session setup. **Capture, Binary**

### Battery and connection status (`04`)

The two response bytes are:

```text
data[0]  battery step, 0..10 (display as step * 10 percent)
data[1]  0 = wireless path, 1 = USB cable/wired path
```

Observed responses include `0a 00`, `0a 01`, `07 01`, and `06 00`. A direct
Linux status query on the connected `25a7:fa07` also returned `06 00`. Capture
filenames and connection state correlate the second byte with cable/wired
operation. It should not be labeled “charging” unless charging is independently
confirmed for a particular firmware. **Capture, Live; cable meaning is strong
Inference**

## Areson EEPROM map

Only the following range is used by the vendor application:

| Address | Size | Meaning | Confidence |
|---:|---:|---|---|
| `0000` | 2 | polling code + record checksum | Capture, Binary |
| `0002` | 2 | enabled DPI-stage count + checksum | Binary; meaning confirmed by layout |
| `0004` | 2 | active/default DPI stage record | Startup read; exact semantics Inference |
| `0006-000b` | 6 | additional DPI state records | Unknown |
| `000c-002b` | 32 | eight possible DPI records, four bytes each | Capture, Binary |
| `002c-005f` | 52 | DPI colors and lighting configuration | Capture, Binary |
| `0060-009f` | 64 | 16 button action records | Capture, Binary |
| `0100-02ff` | 512 | 16 event-definition slots, `0x20` bytes each | Capture, Binary |
| `0300-1aff` | 6144 | 16 macro slots, `0x180` bytes each | Capture, Binary |

The remainder of 64 KiB dumps is predominantly erased `ff` data. Reading it is
useful for research, but it is not evidence for extra Areson profiles.

### Polling rate

The two-byte record at `0x0000` is `[code, 0x55-code]`:

| Rate | Code | Check byte |
|---:|---:|---:|
| 125 Hz | `08` | `4d` |
| 250 Hz | `04` | `51` |
| 500 Hz | `02` | `53` |
| 1000 Hz | `01` | `54` |

The 250/500/1000 writes are directly captured; `08` for 125 is present in the
vendor binary's read/write conversion. The prior `04/02/01/00` table was shifted
and treated a valid `01` code as 500 Hz. **Capture, Binary**

### DPI records

Eight four-byte slots start at `0x000c`:

```text
[x_raw, y_raw, sensor_flag, inner_checksum]
sum(record) & 0xff == 0x55
```

The bundled driver contains sensor-specific DPI lookup tables rather than one
universal linear formula. Its configuration names sensor families `0x3325` and
`0x3335`; the active choice is influenced by the device version/sensor nibble.
Consequently, arbitrary raw-to-DPI interpolation should be described as an
approximation. Exact captured/default anchors include:

```text
default:  1000=0b, 2000=17, 4000=2f, 8000=5f, 10000=bd
captured edits: 1600=12, 2400=1b, 4900=3a, 8900=6a
```

The fifth edited filename is ambiguous (`1410` vs `14100`) and is not used as a
conversion anchor. Raw X/Y and the record checksum are known; a complete
per-sensor DPI table remains an open item. **Capture, Binary**

The application exposes the model-configured one-to-five enabled stages and
writes the two-byte count record at `0x0002` as `[count, 0x55-count]`. Although
the EEPROM layout reserves eight records, the supplied model configuration and
Windows UI expose five; slots six through eight are therefore not presented as
confirmed user-facing stages. **Binary; five-stage model limit is Capture/UI**

### Button action table

There are 16 records at `0x0060 + 4*index`. Every record is:

```text
[type, d1, d2, inner_checksum]
inner_checksum = (0x55 - type - d1 - d2) & 0xff
```

Physical mapping:

| Internal index | Address | Physical control |
|---:|---:|---|
| 0–5 | `0060-0074` | side buttons 1–6 |
| 6 | `0078` | right mouse button |
| 7 | `007c` | left mouse button |
| 8–9 | `0080-0084` | side buttons 7–8 |
| 10 | `0088` | middle mouse button |
| 11 | `008c` | fire button |
| 12–15 | `0090-009c` | side buttons 9–12 |

The physical top DPI buttons are absent from this Areson table. No capture or
vendor configuration entry addresses them, so they appear firmware-fixed on
`25a7:fa07/fa08`. The separate Holtek map does contain DPI Up and DPI Down and
allows them to be assigned keyboard actions. **Capture, Binary**

Action types:

| Type | d1 | d2 | Meaning |
|---:|---|---|---|
| `00` | 0 | 0 | disabled |
| `01` | mouse mask | 0 | native mouse button |
| `02` | 1 loop, 2 up, 3 down | 0 | DPI control |
| `04` | delay ms | repeat count | repeated left click/fire |
| `05` | 0 | 0 | execute this index's event-definition slot |
| `06` | macro slot 0–15 | repeat/mode | execute hardware macro |
| `07` | 0 | 0 | cycle polling rate |
| `08` | 0 | 0 | toggle lighting |
| `09` | 0 | 0 | profile switch in generic vendor code; hidden here |

Mouse masks are `01` left, `02` right, `04` middle, `08` back, and `10`
forward. Thus the exact left-click record is `01 01 00 53`, not one of the old
guessed `f0/f1/f2` records. **Capture, Binary**

### Event-definition slots

Button index `i` has a `0x20`-byte definition block at:

```text
address = 0x0100 + i * 0x20
```

The block begins with an event count, followed by three-byte events and one
inner checksum. Unused bytes remain `ff`:

```text
[count] [status, code_lo, code_hi] ... [checksum] [ff ...]
sum(count through checksum) & 0xff == 0x55
```

Statuses:

- `81` / `41`: keyboard usage down/up
- `80` / `40`: modifier down/up; codes `01/02/04/08` are Ctrl/Shift/Alt/GUI
- `82` / `42`: 16-bit Consumer Page usage down/up

Each modifier is a separate event. For Ctrl+Shift+1, the vendor emits six
events: Ctrl down, Shift down, 1 down, Ctrl up, Shift up, 1 up. A combined
modifier bitmask in one event is not equivalent. **Capture, Binary**

### Macros

There are 16 slots:

```text
slot_address = 0x0300 + slot_index * 0x0180
slot_size    = 384 bytes
```

Layout:

| Offset | Size | Meaning |
|---:|---:|---|
| `00` | 1 | UTF-16LE name length in bytes |
| `01-1e` | 30 | name, zero padded (15 UTF-16 code units) |
| `1f` | 1 | event count |
| `20...` | 5 each | macro events |
| after events | 4 | `[checksum, 00, 00, 00]` |

The apparent `00 03` before the checksum in many traces is the final event's
big-endian 3 ms delay. It is not part of a six-byte terminator.

Each event is:

```text
[status, code, 00, delay_hi, delay_lo]
```

The status high bits encode direction (`80` down, `40` up); the low three bits
encode class:

| Status | Class |
|---:|---|
| `80/40` | modifier |
| `81/41` | keyboard |
| `84/44` | mouse button |

Mouse event codes use the same `01/02/04/08/10` button masks. The bundled UI
enables the first three through `MacroHasMsKey=0x07`; the converter itself also
recognizes back and forward. It rejects other event classes, and the fixed
five-byte representation has no accepted relative-movement class. Native mouse
clicks are therefore supported; mouse movement is not. **Binary; left/right/
middle UI behavior corroborated by issue report**

Terminator checksum:

```python
checksum = (0x55 - event_count - sum(serialized_events)) & 0xff
```

A slot can hold at most 69 events (`32 + 69*5 + 4 = 381`). The vendor forces a
minimum event delay of 3 ms during conversion. **Capture, Binary**

The delay is attached to the event before it. For a simple generated character,
the key-down delay is its hold duration and the key-up delay is the gap before
the next key. The application-level text builder can use one fixed gap or
sample each gap from a user-selected range, then stores those sampled values as
ordinary fixed event delays. Randomness is not a firmware playback feature.

US-layout unshifted characters consume two events. Shifted characters consume
four and use modifier event code `20`, the value seen in captured macro data.
The editor rejects unsupported text or output above 69 events before writing.
**Capture-backed serialization; builder timing policy**

Macro action repeat byte:

- `01..fd`: repeat count
- `fe`: repeat while the physical button is held
- `ff`: toggle/continue until another activation

### Lighting records

The following write shapes are directly observed and are implemented:

- every enabled effect: 8 bytes at `0x0054`, containing RGB + RGB checksum,
  mode + mode checksum, and brightness + brightness checksum;
- off: `00 55` at `0x0058`;
- Respiration and Neon: an additional speed + speed-checksum pair at `0x005c`.

The Areson mode byte is `01` Steady, `02` Respiration/Breathing, and `03`
Neon. This differs from the application's older public constant ordering, so
the protocol layer translates the two animated values instead of exposing a
silent label swap. Captures exercise animation-speed values `01..05` (fast to
slow); the UI now writes both required records for either animated effect.

All inner two-/four-/eight-byte records retain the `sum == 0x55` invariant.
The Windows captures leave roughly 25–35 ms between an acknowledgement and
the next feature report. The implementation uses a conservative 50 ms settle
interval for reliable write sequences. Without that gap the receiver may
acknowledge and persist a lighting record without reloading the active LED
engine until its physical lighting switch is cycled.
The generic vendor binary also contains “stream”/main-lighting branches, but
this mouse's configuration hides some of them. Those branches should not be
claimed as confirmed Areson features until a matching capture exists.

The absolute lowest captured steady-light brightness pair is `01 54`
(brightness byte plus its `0x55` complement), but hardware testing found that
green overwhelms red at that PWM floor and mixed yellow/orange colors appear
pure green. Battery LED mode therefore uses the next capture-confirmed low
setting, 10% (`1e 37`). Its application-level color mapping is full-saturation
red at 0%, yellow at 50%, and green at 100%, linearly interpolated through
orange/yellow-green. Because status command `04` reports only 11 levels, the
physical LED has 11 gradient steps. The controller writes only when that level
changes and restores the previous lighting on a normal exit; no separate
volatile Areson LED command has been confirmed. **Capture; live hardware;
controller policy**

Wireless firmware may extinguish RGB after inactivity even with a steady
record selected. The vendor UI/configuration contains no idle-time or
always-on control, so the application does not pretend that the EEPROM record
can disable that firmware power-saving behavior and does not use repeated
EEPROM writes as a keepalive. **Vendor binary/configuration; live hardware**

## Holtek summary (`04d9:fc55`)

The Holtek device uses interface 2, report `02` (16 bytes) and report `03` (64
bytes), with feature-report reads rather than Areson's interrupt response. Its
commands are:

- `f1` write control/commit categories
- `f2` memory read
- `f3` memory write
- `f5` polling rate

It has five real hardware profiles and a 20-entry button map. Entries 4 and 5
(zero-based indices) are physical DPI Up and DPI Down, so those controls can be
rebound. Areson profile bases, checksums, command `04`, and macro layout do not
apply to it. See `holtek_protocol.py` for the complete implemented map.

Confirmed Holtek profile data represented by the UI now includes:

- the active profile at `0x003d` and five profile bases;
- 1–10 DPI entries per profile, with `[count, 00, current_index, 00]` headers;
- six-byte DPI entries `[01, raw_dpi, color_index, 00, 00, 00]`, where one raw
  unit is 200 DPI;
- per-profile lighting records `[80, R, G, B, mode, brightness, speed, 03]`;
- physical Profile Switch (`8d`), DPI Up (`8a`), and DPI Down (`89`) button
  actions.

When editing Holtek DPI, the application preserves the read color indices and
current stage instead of zeroing both fields. Effect speed is exposed as a raw
byte because its storage location is known but its user-facing scale is
firmware-defined. Holtek keyboard-button records contain one HID usage and no
modifier field. **Binary, live implementation history**

## Protocol-to-UI coverage

| Capability | Areson UI | Holtek UI |
|---|---|---|
| Physical button map | 16 mapped controls | 19 physical entries (unused slot hidden) |
| Keyboard binding | key + Ctrl/Shift/Alt/GUI | one key; modifiers disabled |
| Mouse actions | left/right/middle/back/forward | left/right/middle/back/forward |
| DPI button actions | loop/up/down on mapped controls | up/down, including physical top buttons |
| Profile switching | generic type hidden for this one-profile model | confirmed `8d` action exposed |
| Hardware macros | 16 slots, editor and repeat modes | disabled; no compatible format confirmed |
| Polling | 125/250/500/1000 Hz | 125/250/500/1000 Hz |
| Lighting | color, known modes, brightness/speed, battery gauge | per-profile color/mode/brightness/speed |
| Raw reports | 17-byte diagnostic tab | disabled to prevent cross-protocol packets |

Generic binary branches without matching model evidence remain hidden. In
particular, Areson type `09`, its extra reserved DPI records, and the generic
“stream” lighting branch are not surfaced merely because code exists in the
shared vendor utility.

## Remaining unknowns

- Exact user-facing meaning of Areson records `0x0004..0x000b`.
- Complete DPI lookup tables for every Areson sensor/version combination.
- Whether the generic vendor “stream” lighting path is reachable on this exact
  firmware.
- Whether macro back/forward events are accepted by firmware as well as by the
  vendor converter (left/right/middle are the supported UI subset).

These are intentionally marked unknown rather than filled with guessed magic
values.

## Reproducing the analysis

`tools/decode_areson_pcap.py` decodes report framing, checksums, addresses, and
known regions directly from the repository's USBPcap files. For example:

```bash
python3 tools/decode_areson_pcap.py \
  "usbcap/usb polling rate from 125 to 250 to 500 to 1000.pcapng" --hex
```

The binary analysis used the bundled 32-bit
`UtechSmart/Venus wireless/OemDrv.exe` (SHA-256
`28bab71de7267c0872f8c54baeb14bfdae0859ee6dabf309067c95ae7ea3d8c8`). The
Ghidra post-scripts `GhidraProtocolExport.java`, `GhidraDecompileRange.java`,
and `GhidraDumpMemory.java` under `tools/` reproduce the string-xref,
decompilation, and lookup-table extraction steps.

For live troubleshooting without EEPROM writes, `tools/diagnose_device.py`
lists the chosen configuration interface. Its optional `--battery` flag sends
only status command `0x04`.
