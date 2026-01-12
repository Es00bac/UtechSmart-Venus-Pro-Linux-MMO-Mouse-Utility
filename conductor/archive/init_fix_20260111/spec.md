# Track Spec: Resolve Initialization Connection Instability

## Overview
The Venus Pro configuration utility is experiencing intermittent "Flash read timeout" errors at the beginning of the device initialization sequence (`Page=0x00 Offset=0x00`). This issue emerged following the implementation of staged button remapping. The instability affects both wired and wireless connections, requiring multiple manual reconnection attempts or hardware resets (unplugging) to establish a successful session.

## Functional Requirements
*   **Stabilize Startup Sequence:** Identify and resolve the race condition or protocol conflict causing the initial flash read to time out.
*   **Robust Device Handshaking:** Refine the handshake logic (`0x03` / `0x04` commands) used during the `_read_settings` phase to ensure the device is ready for data transfer.
*   **Improve Error Recovery:** Implement a more graceful retry mechanism in the GUI when a read fails, reducing the need for manual "Reconnect" clicks.
*   **Diagnostic Logging:** Ensure startup events (like the "Unlock" sequence) are logged to the UI console for better transparency.

## Technical Analysis (Hypothesis)
The issue likely stems from a conflict between the PyUSB-based `unlock_device()` call and the subsequent `hidapi`-based `read_flash()` calls in `_read_settings`. Since `unlock_device()` is called just before `_refresh_and_connect()`, the device may still be resetting or re-enumerating when the first read request arrives.

## Acceptance Criteria
*   The utility consistently detects and reads settings from both wired and wireless devices on the first launch attempt.
*   The "Flash read timeout at Page=0x00 Offset=0x00" error is eliminated during normal operation.
*   The "Running Startup Unlock..." message is visible in the UI log (if the unlock logic is executed).
