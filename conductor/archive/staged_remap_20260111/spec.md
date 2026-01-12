# Track Spec: Staged Button Remapping & Atomic Transactions

## Overview
The current button remapping workflow requires an immediate "Apply" after each individual button binding change. This is inefficient for users who want to remap multiple buttons (e.g., the 12-button side panel) in one go. This track refactors the configuration logic to support a "staging" area in the UI and an "atomic" write process to the device.

## Objectives
*   Implement a staging mechanism in `venus_gui.py` to hold pending binding changes.
*   Update the UI to provide visual cues for staged but unapplied changes.
*   Refactor `venus_protocol.py` or the communication logic to handle batch updates as a single atomic transaction where possible.
*   Ensure that failures during batch application do not leave the device in an inconsistent state.

## Requirements
*   **Staging Area:** A data structure to hold pending changes (e.g., a dictionary of button index to new binding).
*   **Batch Apply Button:** A dedicated "Apply Changes" button that is enabled only when staged changes exist.
*   **Cancel Changes:** A "Discard" button to clear the staging area without modifying the device.
*   **Atomic Write Logic:** Logic to iterate through staged changes and apply them sequentially, with verification at each step.
*   **Transaction Logging:** Detailed logging of the batch process for auditability.

## Technical Considerations
*   The `VenusProtocol` class should be extended or wrapped to support transaction-like behavior.
*   PyQt6 signals and slots will need updating to manage the state of the "Apply" button based on the staging area's content.
*   Existing unit tests must be updated, and new tests must be written to cover batch application and error recovery.
