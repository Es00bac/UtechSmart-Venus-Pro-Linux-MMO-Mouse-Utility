# Track Plan: Resolve Initialization Connection Instability

This plan details the steps to identify and fix the connection instability and flash read timeouts during utility startup.

## Phase 1: Diagnostics & Root Cause Analysis [checkpoint: 49bea58]
Goal: Isolate the cause of the timeout (Protocol sequence vs. Hardware timing).

- [x] Task: Enhanced Startup Logging (Modify `venus_gui.py` to log the exact timing and results of `unlock_device` and initial handshakes)
- [x] Task: Reproduce with Script (Create a standalone test script `tests/debug_init.py` that only performs the startup sequence to isolate it from the GUI event loop)
- [x] Task: Conductor - User Manual Verification 'Phase 1: Diagnostics' (Protocol in workflow.md) 49bea58

## Phase 2: Protocol Stabilization
Goal: Refine the handshake and read logic to ensure reliability.

- [ ] Task: Write Tests for Handshake Reliability (Verify that the device responds correctly to repeated 0x03/0x04 sequences)
- [ ] Task: Implement Handshake Retries (Update `venus_protocol.py` or `venus_gui.py` to retry the initial handshake if the first one fails)
- [ ] Task: Add Timing Delays (Introduce small, configurable delays after `unlock_device` or `0x03` handshake if needed to allow device stabilization)
- [ ] Task: Conductor - User Manual Verification 'Phase 2: Stabilization' (Protocol in workflow.md)

## Phase 3: GUI Integration & Polish
Goal: Ensure the fix is robust within the main application.

- [ ] Task: Refactor `_read_settings` Initialization (Move blocking calls to a safer point in the lifecycle or ensure they handle timeouts gracefully)
- [ ] Task: Final UX Verification (Verify that the 'Ready' status and initial read succeed consistently on both Wired/Wireless)
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Integration' (Protocol in workflow.md)
