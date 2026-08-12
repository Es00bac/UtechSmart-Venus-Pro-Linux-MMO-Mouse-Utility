# Macro editor guide

The macro editor writes the Areson/Compx hardware macro format used by
`25a7:fa07` and `25a7:fa08`. The separate Holtek `04d9:fc55` controller has no
confirmed compatible macro storage format, so the app disables this tab for
that device rather than sending Areson reports to it.

## Hardware limits

- 16 device slots
- 384 bytes per slot
- 69 events maximum per slot
- 5 bytes per event
- 3 ms minimum generated delay
- 15 UTF-16 code units per hardware name

A normal key uses two events: press, then release. A shifted character uses
four: Shift press, key press, Shift release, and key release. The capacity bar
shows the exact hardware-event cost before a write.

## Text Builder

Enter text using a US keyboard layout, then choose:

- **Fixed** — every key-to-key gap is the same.
- **Random range** — each gap is sampled independently between the minimum and
  maximum values when **Generate Text Events** is clicked.
- **Key held** — time between a key press and its release.
- **Extra after spaces** — an additional pause after spaces, newlines, carriage
  returns, and tabs.
- **Replace** or **Append** — replace the current event list or add the text to
  its end.

The builder supports printable US-layout ASCII plus Enter and Tab. It rejects
unsupported characters and over-capacity output before modifying the table.
The final event is normalized to the capture-confirmed 3 ms end delay when the
macro is saved.

Random timing is generated locally during conversion. Once saved, the sampled
delays are ordinary fixed values in the mouse's EEPROM; the mouse does not
generate new random delays during playback.

## Recording and manual events

**Record** captures supported keyboard press/release events and the elapsed
time after the preceding event. Ctrl, Shift, Alt, and GUI/Super modifier
presses and releases are stored as their own hardware events, so combinations
such as Ctrl+C and Ctrl+Alt+Delete preserve their ordering and timing. Left and
right Ctrl, Shift, and Alt have separate vendor codes when Qt supplies enough
native key information to distinguish them. The firmware has only one shared
GUI/Super code.

The **Manual Events** builder can add:

- keyboard keys;
- left/right Ctrl, Shift, and Alt plus the shared GUI/Super modifier;
- left, right, middle, back, and forward mouse-button masks;
- a complete tap, a press only, or a release only.

**Tap** creates a matched press/release pair. Press-only and release-only are
available for intentionally overlapping events; the preview warns if a macro
ends while an input is still held.

The vendor converter recognizes the five mouse-button masks. Left, right, and
middle clicks are corroborated by the vendor UI and project issue reports;
back and forward are converter-supported but have less firmware evidence.
There is no accepted event class for relative pointer movement, so mouse
movement is intentionally not offered.

## Editing

- Edit any event's **Delay after** value directly.
- Apply one delay to multiple selected rows.
- Reorder, duplicate, or delete events with the toolbar.
- Use `Delete`, `Ctrl+D`, `Alt+Up`, and `Alt+Down` from the event table.
- Watch the output preview, total duration, unmatched-input warning, and
  capacity bar while editing.

## Slots and binding

Selecting a slot chooses the save target but does not perform surprise device
I/O. Double-click a slot or click **Load from Mouse** to replace the editor with
that slot's EEPROM contents. Click **Save to Mouse** to write the name and
events.

After saving, bind the slot to a physical button with one of four playback
modes:

- run once;
- repeat a fixed count (`1..253`);
- repeat while held (`0xfe`);
- toggle looping (`0xff`).

Slot selection in the Macros tab is isolated from the Buttons tab, so browsing
or editing a macro cannot silently restage an unrelated button binding.
