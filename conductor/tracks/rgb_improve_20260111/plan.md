# Track Plan: Improve RGB Functionality

This plan details the steps to reverse-engineer and implement accurate RGB control, including the 27 standard presets and arbitrary color picking.

## Phase 1: Protocol Analysis & Documentation [checkpoint: c5f7328]
Goal: Extract the exact RGB command structure and color formula from packet captures.

- [x] Task: Analyze RGB Captures (Extract raw bytes for the 27 Quick Pick colors from `new-usbcap/*.pcapng`) <!-- id: 0 -->
- [x] Task: Reverse-Engineer Color Formula (Determine if the mouse uses standard RGB, GRB, or a custom mapping/normalization) <!-- id: 1 -->
- [x] Task: Update `PROTOCOL.md` (Document the refined RGB packet structure and the 27 preset values)
- [x] Task: Conductor - User Manual Verification 'Phase 1: Analysis' (Protocol in workflow.md) c5f7328

## Phase 2: Protocol Implementation (TDD) [checkpoint: 1a27522]
Goal: Update the core protocol library to support the new RGB logic.

- [x] Task: Write Tests for RGB Packet Building (Define expected bytes for known presets and arbitrary colors) 86481ec
- [x] Task: Refactor `venus_protocol.py` RGB Logic (Implement the `build_rgb` function using the discovered formula)
- [x] Task: Verify Protocol Tests (Ensure all RGB packet tests pass with high coverage)
- [x] Task: Conductor - User Manual Verification 'Phase 2: Protocol' (Protocol in workflow.md) 1a27522

## Phase 3: GUI Refactor (TDD)
Goal: Enhance the RGB tab with a preset grid and accurate color picker.

- [x] Task: Write UI Tests for RGB Tab (Verify preset grid population and color picker signal handling) c3526a8
- [x] Task: Implement Preset Grid (Add a grid of 27 swatches to the RGB tab for quick access) 7682f85
- [x] Task: Update Color Picker Integration (Connect the native color picker to the refined protocol logic)
- [x] Task: Final UX Polish (Ensure tooltips and labels accurately reflect the new capabilities) 577fc0f
- [ ] Task: Conductor - User Manual Verification 'Phase 3: GUI Refactor' (Protocol in workflow.md)
