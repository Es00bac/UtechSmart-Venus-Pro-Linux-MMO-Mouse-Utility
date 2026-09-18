"""Offline checks for the UI-independent macro draft model."""

from __future__ import annotations

import os
import random
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import venus_macro_draft as md  # noqa: E402
import venus_protocol as vp  # noqa: E402


class MacroDraftTests(unittest.TestCase):
    def setUp(self):
        self.draft = md.MacroDraft()

    def test_fixed_text_generation_and_append(self):
        self.draft.generate_text("ab", key_hold_ms=35, delay_min_ms=90,
                                 delay_max_ms=90, extra_word_pause_ms=0, append=False)
        events = self.draft.to_macro_events()
        self.assertEqual([event.delay_ms for event in events], [35, 90, 35, 3])
        self.assertEqual(self.draft.preview().output, "ab")

        self.draft.generate_text("c", key_hold_ms=35, delay_min_ms=90,
                                 delay_max_ms=90, extra_word_pause_ms=0, append=True)
        self.assertEqual(len(self.draft), 6)
        self.assertEqual(vp.macro_events_to_text(self.draft.to_macro_events()), "abc")

    def test_random_text_timing_is_reproducible_with_rng(self):
        self.draft.generate_text("hi", key_hold_ms=35, delay_min_ms=70,
                                 delay_max_ms=160, extra_word_pause_ms=80,
                                 append=False, rng=random.Random(7))
        delays = [event.delay_ms for event in self.draft.to_macro_events()]
        self.assertEqual(delays[0], 35)
        self.assertTrue(70 <= delays[1] <= 160, delays)
        self.assertEqual(delays[-1], vp.MACRO_MIN_DELAY_MS)

    def test_mouse_tap_creates_matched_pair(self):
        self.assertTrue(self.draft.add_tap("Mouse: Left Button", "mouse", 0x01, 25, 120))
        self.assertEqual(self.draft.to_macro_events(), [
            vp.MacroEvent.mouse(0x01, True, 25),
            vp.MacroEvent.mouse(0x01, False, 120),
        ])
        preview = self.draft.preview()
        self.assertIn("[Left click]", preview.output)
        self.assertEqual(preview.pressed, 0)

    def test_press_only_warns_when_unreleased(self):
        self.draft.add_single("A", "keyboard", vp.HID_KEY_USAGE["A"], True, 90)
        self.assertEqual(self.draft.preview().pressed, 1)
        self.assertIn("still pressed", self.draft.preview().summary)

    def test_modifier_combination_preview(self):
        ctrl = vp.MACRO_MODIFIER_CODES["Left Ctrl"]
        self.draft.add_single("Modifier: Left Ctrl", "modifier", ctrl, True, 3)
        self.draft.add_tap("C", "keyboard", vp.HID_KEY_USAGE["C"], 35, 3)
        self.draft.add_single("Modifier: Left Ctrl", "modifier", ctrl, False, 3)
        self.assertEqual(self.draft.preview().output, "[Left Ctrl+C]")
        self.assertEqual(
            [(e.keycode, e.is_down, e.is_modifier) for e in self.draft.to_macro_events()],
            [(ctrl, True, True), (vp.HID_KEY_USAGE["C"], True, False),
             (vp.HID_KEY_USAGE["C"], False, False), (ctrl, False, True)])

    def test_capacity_is_enforced(self):
        self.draft.generate_text("a" * 34, key_hold_ms=35, delay_min_ms=90,
                                 delay_max_ms=90, extra_word_pause_ms=0, append=False)
        self.assertEqual(len(self.draft), 68)
        self.assertTrue(self.draft.can_add(1))
        self.assertFalse(self.draft.can_add(2))
        self.assertFalse(self.draft.add_tap("A", "keyboard", 0x04, 35, 90))
        self.assertEqual(len(self.draft), 68)
        message, error = self.draft.text_status("a", 90, 90, 0, append=True)
        self.assertIn("holds 69", error)
        message, error = self.draft.text_status("\N{SNOWMAN}", 90, 90, 0, append=False)
        self.assertIn("Unsupported", error)
        message, error = self.draft.text_status("", 90, 90, 0, append=False)
        self.assertEqual(error, "")
        self.assertIn("1 hardware events available", message)
        with self.assertRaises(ValueError):
            self.draft.generate_text("ab", key_hold_ms=35, delay_min_ms=90,
                                     delay_max_ms=90, extra_word_pause_ms=0, append=True)
        self.assertEqual(len(self.draft), 68)

    def test_row_editing_operations(self):
        for name in ("A", "B", "C"):
            self.draft.add_single(name, "keyboard", vp.HID_KEY_USAGE[name], True, 10)
        self.assertEqual(self.draft.move(0, 1), 1)
        self.assertEqual([e.key_name for e in self.draft.events], ["B", "A", "C"])
        self.assertIsNone(self.draft.move(0, -1))
        self.assertEqual(self.draft.duplicate(2), 3)
        self.assertEqual([e.key_name for e in self.draft.events], ["B", "A", "C", "C"])
        self.draft.set_delays([0, 3], 500)
        self.assertEqual([e.delay_ms for e in self.draft.events], [500, 10, 10, 500])
        self.assertEqual(self.draft.delete([1, 1, 3]), 2)
        self.assertEqual([e.key_name for e in self.draft.events], ["B", "C"])
        self.draft.normalize_final_delay()
        self.assertEqual(self.draft.events[-1].delay_ms, vp.MACRO_MIN_DELAY_MS)

    def test_slot_image_round_trip(self):
        source = md.MacroDraft()
        source.generate_text("Hi!", key_hold_ms=35, delay_min_ms=90,
                             delay_max_ms=90, extra_word_pause_ms=0, append=False)
        source.add_tap("Mouse: Right Button", "mouse", 0x02, 20, 3)
        image = vp.build_macro_image("Greet", source.to_macro_events())
        image = image.ljust(vp.MACRO_SLOT_SIZE, b"\xff")

        name, warnings = self.draft.load_slot_image(image)
        self.assertEqual(name, "Greet")
        self.assertEqual(warnings, [])
        self.assertEqual(self.draft.to_macro_events(), source.to_macro_events())
        self.assertEqual(self.draft.preview().output, "Hi![Right click]")

    def test_slot_image_reports_bad_checksum_and_impossible_count(self):
        image = bytearray(vp.MACRO_SLOT_SIZE)
        image[0x1F] = 1
        image[0x20:0x25] = bytes((0x81, 0x04, 0x00, 0x00, 0x03))
        image[0x25] = 0x00  # wrong terminator checksum
        name, warnings = self.draft.load_slot_image(bytes(image))
        self.assertIsNone(name)
        self.assertEqual(len(warnings), 1)
        self.assertEqual(len(self.draft), 1)

        image[0x1F] = 200
        with self.assertRaises(vp.ProtocolError):
            self.draft.load_slot_image(bytes(image))

    def test_manual_choices_expose_every_hardware_modifier(self):
        modifiers = {label: code for label, kind, code in md.manual_event_choices()
                     if kind == "modifier"}
        self.assertEqual(modifiers, {
            f"Modifier: {name}": code for name, code in vp.MACRO_MODIFIER_CODES.items()})
        mouse = [code for _, kind, code in md.manual_event_choices() if kind == "mouse"]
        self.assertEqual(mouse, [0x01, 0x02, 0x04, 0x08, 0x10])


if __name__ == "__main__":
    unittest.main()
