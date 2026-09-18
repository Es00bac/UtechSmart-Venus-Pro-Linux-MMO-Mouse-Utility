"""UI-independent model of the macro being edited.

``MacroDraft`` holds the ordered press/release stream shown in the macro
editor of either front end, enforces the hardware slot capacity, renders the
text preview, converts to and from ``venus_protocol.MacroEvent`` and parses a
raw EEPROM slot image.  It imports only :mod:`venus_protocol`, so it is
testable without Qt and without a mouse.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from typing import Iterable

import venus_protocol as vp

# Reverse map for HID names.  The first mapping wins so the macro-only
# "Shift" alias (0x20) cannot override "3".
HID_USAGE_TO_NAME: dict[int, str] = {}
for _key_name, _code in vp.HID_KEY_USAGE.items():
    HID_USAGE_TO_NAME.setdefault(_code, _key_name)

MOUSE_BUTTON_NAMES: dict[int, str] = {
    0x01: "Mouse: Left Button",
    0x02: "Mouse: Right Button",
    0x04: "Mouse: Middle Button",
    0x08: "Mouse: Back Button",
    0x10: "Mouse: Forward Button",
}
MOUSE_CLICK_NAMES: dict[int, str] = {
    0x01: "Left click", 0x02: "Right click", 0x04: "Middle click",
    0x08: "Back click", 0x10: "Forward click",
}


def modifier_display_name(keycode: int) -> str:
    name = vp.MACRO_MODIFIER_NAMES.get(keycode)
    return f"Modifier: {name}" if name else f"Modifier 0x{keycode:02X}"


def keyboard_display_name(keycode: int) -> str:
    return HID_USAGE_TO_NAME.get(keycode, f"Key 0x{keycode:02X}")


def mouse_display_name(keycode: int) -> str:
    return MOUSE_BUTTON_NAMES.get(keycode, f"Mouse: Button 0x{keycode:02X}")


@dataclass(frozen=True)
class DraftEvent:
    """One row of the editor: a display name plus the hardware event data."""
    key_name: str
    is_down: bool
    delay_ms: int
    is_modifier: bool = False
    event_type: str = "keyboard"  # keyboard, modifier, or mouse
    keycode: int | None = None

    @property
    def kind(self) -> str:
        return "modifier" if self.is_modifier else self.event_type

    def to_macro_event(self) -> vp.MacroEvent | None:
        if self.event_type == "mouse" and self.keycode is not None:
            return vp.MacroEvent.mouse(int(self.keycode), self.is_down, self.delay_ms)
        if self.key_name in vp.HID_KEY_USAGE or self.keycode is not None:
            keycode = (int(self.keycode) if self.keycode is not None
                       else vp.HID_KEY_USAGE[self.key_name])
            return vp.MacroEvent(
                keycode=keycode, is_down=self.is_down, delay_ms=self.delay_ms,
                is_modifier=self.is_modifier, event_type=self.event_type)
        return None

    @classmethod
    def from_macro_event(cls, event: vp.MacroEvent) -> "DraftEvent":
        kind = "modifier" if event.is_modifier else event.event_type
        if kind == "modifier":
            name = modifier_display_name(event.keycode)
        elif kind == "mouse":
            name = mouse_display_name(event.keycode)
        else:
            name = keyboard_display_name(event.keycode)
        return cls(name, event.is_down, event.delay_ms, event.is_modifier,
                   event.event_type, event.keycode)


@dataclass(frozen=True)
class DraftPreview:
    output: str
    total_ms: int
    pressed: int

    @property
    def summary(self) -> str:
        rendered = json.dumps(self.output, ensure_ascii=False)
        warning = f" · ⚠ {self.pressed} still pressed" if self.pressed else ""
        return f"Output: {rendered} · {self.total_ms:,} ms total{warning}"


def manual_event_choices() -> list[tuple[str, str, int]]:
    """Every event the manual builder offers: (label, event_type, code)."""
    choices: list[tuple[str, str, int]] = [
        (name, "mouse", code) for code, name in MOUSE_BUTTON_NAMES.items()]
    for modifier_name, modifier_code in vp.MACRO_MODIFIER_CODES.items():
        choices.append((f"Modifier: {modifier_name}", "modifier", modifier_code))
    manual_keys = sorted(
        ((name, code) for code, name in HID_USAGE_TO_NAME.items()
         if code < 0xE0 and name != "Shift"),
        key=lambda item: (len(item[0]) > 1, item[0]),
    )
    choices.extend((name, "keyboard", code) for name, code in manual_keys)
    return choices


class MacroDraft:
    """The ordered event list of the macro editor, capped at the slot size."""

    capacity = vp.MACRO_MAX_EVENTS

    def __init__(self) -> None:
        self.events: list[DraftEvent] = []

    # -- capacity ---------------------------------------------------------
    def __len__(self) -> int:
        return len(self.events)

    @property
    def free(self) -> int:
        return self.capacity - len(self.events)

    def can_add(self, count: int) -> bool:
        return len(self.events) + count <= self.capacity

    # -- editing ----------------------------------------------------------
    def add(self, event: DraftEvent, row: int | None = None) -> bool:
        """Insert one event (at the end by default) unless the slot is full."""
        if not self.can_add(1):
            return False
        if row is None:
            row = len(self.events)
        row = max(0, min(row, len(self.events)))
        self.events.insert(row, event)
        return True

    def add_single(self, key_name: str, event_type: str, keycode: int,
                   is_down: bool, delay_ms: int) -> bool:
        return self.add(DraftEvent(key_name, is_down, delay_ms,
                                   event_type == "modifier", event_type, keycode))

    def add_tap(self, key_name: str, event_type: str, keycode: int,
                hold_ms: int, delay_ms: int) -> bool:
        """Add a matched press/release pair; both or neither are added."""
        if not self.can_add(2):
            return False
        self.add_single(key_name, event_type, keycode, True, hold_ms)
        self.add_single(key_name, event_type, keycode, False, delay_ms)
        return True

    def delete(self, rows: Iterable[int]) -> int:
        removed = 0
        for row in sorted(set(rows), reverse=True):
            if 0 <= row < len(self.events):
                del self.events[row]
                removed += 1
        return removed

    def clear(self) -> None:
        self.events.clear()

    def duplicate(self, row: int) -> int | None:
        """Copy a row below itself; returns the new row or None when full."""
        if not 0 <= row < len(self.events) or not self.can_add(1):
            return None
        self.events.insert(row + 1, self.events[row])
        return row + 1

    def move(self, row: int, delta: int) -> int | None:
        """Swap a row with a neighbour; returns its new row or None."""
        target = row + delta
        if not (0 <= row < len(self.events) and 0 <= target < len(self.events)):
            return None
        self.events[row], self.events[target] = self.events[target], self.events[row]
        return target

    def set_delay(self, row: int, delay_ms: int) -> bool:
        if not 0 <= row < len(self.events):
            return False
        delay_ms = max(0, min(0xFFFF, int(delay_ms)))
        self.events[row] = replace(self.events[row], delay_ms=delay_ms)
        return True

    def set_delays(self, rows: Iterable[int], delay_ms: int) -> None:
        for row in rows:
            self.set_delay(row, delay_ms)

    def normalize_final_delay(self) -> None:
        """The last event always carries the capture-confirmed 3 ms delay."""
        if self.events:
            self.set_delay(len(self.events) - 1, vp.MACRO_MIN_DELAY_MS)

    # -- conversion -------------------------------------------------------
    def to_macro_events(self) -> list[vp.MacroEvent]:
        events = []
        for draft in self.events:
            event = draft.to_macro_event()
            if event is not None:
                events.append(event)
        return events

    def extend_from_macro_events(self, events: Iterable[vp.MacroEvent],
                                 append: bool = True) -> int:
        """Append (or replace with) converted events; all or nothing."""
        converted = [DraftEvent.from_macro_event(event) for event in events]
        existing = len(self.events) if append else 0
        if existing + len(converted) > self.capacity:
            raise ValueError(
                f"Generation would need {existing + len(converted)} events; "
                f"the slot holds {self.capacity}.")
        if not append:
            self.events.clear()
        self.events.extend(converted)
        return len(converted)

    # -- preview ----------------------------------------------------------
    def preview(self) -> DraftPreview:
        """Text output, total duration and the count of unreleased inputs."""
        events = self.to_macro_events()
        total_delay = sum(event.delay_ms for event in events)
        output: list[str] = []
        pressed: set[tuple[str, int]] = set()
        active_modifiers: set[int] = set()

        for event in events:
            kind = "modifier" if event.is_modifier else event.event_type
            identity = (kind, event.keycode)
            if event.is_down:
                pressed.add(identity)
            else:
                pressed.discard(identity)

            if kind == "modifier":
                if event.is_down:
                    active_modifiers.add(event.keycode)
                else:
                    active_modifiers.discard(event.keycode)
            elif kind == "mouse" and event.is_down:
                output.append(
                    f"[{MOUSE_CLICK_NAMES.get(event.keycode, 'Mouse click')}]")
            elif kind == "keyboard" and event.is_down:
                non_text = active_modifiers.intersection(
                    vp.MACRO_NON_TEXT_MODIFIER_CODES)
                if non_text:
                    labels = "+".join(
                        vp.MACRO_MODIFIER_NAMES.get(code, f"0x{code:02X}")
                        for code in sorted(active_modifiers))
                    output.append(f"[{labels}+{keyboard_display_name(event.keycode)}]")
                else:
                    shift_active = bool(
                        active_modifiers.intersection(vp.MACRO_SHIFT_CODES))
                    character = vp.ASCII_FROM_HID.get(
                        (event.keycode, shift_active))
                    if character is not None:
                        output.append(character)
                    else:
                        output.append(f"[{keyboard_display_name(event.keycode)}]")
        return DraftPreview("".join(output), total_delay, len(pressed))

    # -- text builder -----------------------------------------------------
    def text_status(self, text: str, delay_min: int, delay_max: int,
                    word_pause: int, append: bool) -> tuple[str, str]:
        """Return (message, error) for the text builder; error is "" when OK."""
        required, unsupported = vp.text_macro_requirements(text)
        existing = len(self.events)
        total = existing + required if append else required
        error = ""
        if not text:
            message = (f"US keyboard layout · {self.capacity - existing} "
                       "hardware events available in this slot")
        elif unsupported:
            display = ", ".join(repr(character) for character in unsupported)
            error = f"Unsupported character(s): {display}"
            message = error
        elif delay_min > delay_max:
            error = "The random minimum cannot exceed the maximum."
            message = error
        elif delay_max + word_pause > 0xFFFF:
            error = "The inter-key delay plus word pause exceeds 65,535 ms."
            message = error
        elif total > self.capacity:
            error = (f"Needs {total} events after generation; the hardware "
                     f"slot holds {self.capacity}.")
            message = error
        else:
            verb = "append" if append else "replace"
            message = (f"{len(text)} character(s) → {required} events · "
                       f"{self.capacity - total} free after {verb}")
        return message, error

    def generate_text(self, text: str, *, key_hold_ms: int, delay_min_ms: int,
                      delay_max_ms: int, extra_word_pause_ms: int,
                      append: bool, rng=None) -> int:
        """Convert text to events; raises ValueError with a user message."""
        events = vp.build_text_macro_events(
            text, key_hold_ms=key_hold_ms, delay_min_ms=delay_min_ms,
            delay_max_ms=delay_max_ms, extra_word_pause_ms=extra_word_pause_ms,
            rng=rng)
        return self.extend_from_macro_events(events, append=append)

    # -- EEPROM slot image ------------------------------------------------
    def load_slot_image(self, raw_macro: bytes) -> tuple[str | None, list[str]]:
        """Replace the draft with a 0x180-byte slot; returns (name, warnings).

        The name is ``None`` when the slot carries no decodable name.
        Raises ``venus_protocol.ProtocolError`` for an impossible event count.
        """
        warnings: list[str] = []
        name: str | None = None
        name_length = raw_macro[0]
        if 0 < name_length <= 30 and name_length % 2 == 0:
            try:
                name = raw_macro[1:1 + name_length].decode("utf-16le")
            except UnicodeDecodeError:
                name = None

        event_count = raw_macro[0x1F]
        if event_count > self.capacity:
            raise vp.ProtocolError(
                f"macro slot reports impossible event count {event_count}")
        event_offset = vp.MACRO_HEADER_SIZE
        events_end = event_offset + event_count * 5
        expected = vp.calculate_terminator_checksum(raw_macro, event_count)
        if events_end < len(raw_macro) and raw_macro[events_end] != expected:
            warnings.append(
                f"macro checksum is invalid (stored {raw_macro[events_end]:02x}, "
                f"expected {expected:02x})")

        self.events.clear()
        for _ in range(event_count):
            if event_offset + 5 > vp.MACRO_SLOT_SIZE:
                break
            status = raw_macro[event_offset]
            keycode = raw_macro[event_offset + 1]
            if status not in (0x81, 0x41, 0x80, 0x40, 0x84, 0x44):
                break
            delay = (raw_macro[event_offset + 3] << 8) | raw_macro[event_offset + 4]
            is_down = bool(status & 0x80)
            is_modifier = status in (0x80, 0x40)
            is_mouse = (status & 0x07) == 0x04
            if is_mouse:
                self.add(DraftEvent(mouse_display_name(keycode), is_down, delay,
                                    False, "mouse", keycode))
            elif is_modifier:
                self.add(DraftEvent(modifier_display_name(keycode), is_down,
                                    delay, True, "modifier", keycode))
            else:
                self.add(DraftEvent(keyboard_display_name(keycode), is_down,
                                    delay, False, "keyboard", keycode))
            event_offset += 5
        return name, warnings
