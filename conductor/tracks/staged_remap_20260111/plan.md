# Track Plan: Staged Button Remapping & Atomic Transactions

This plan outlines the steps to refactor the button remapping workflow to support staged batch application and atomic transactions.

## Phase 1: Core Logic & Staging Mechanism [checkpoint: 6fb603b]
Goal: Implement the backend data structures and logic to support staging changes without immediate device writes.

- [x] Task: Write Tests for Staging Data Structure (Define expected behavior for adding, removing, and clearing staged bindings) <!-- id: 0 --> 38a7c2e
- [x] Task: Implement Staging Area Logic (Add data structures to track pending changes in the UI state) a5f09ae
- [x] Task: Write Tests for Atomic Transaction Logic (Define expected behavior for successful and failed batch applications) b809482
- [x] Task: Implement Atomic Transaction Controller (Logic to iterate and apply staged changes with verification) 5f6c101
- [x] Task: Conductor - User Manual Verification 'Phase 1: Core Logic' (Protocol in workflow.md) 6fb603b

## Phase 2: UI Refactor & Integration
Goal: Update the PyQt6 interface to support the new staged workflow.

- [ ] Task: Write UI Tests for Staging Visuals (Verify "Apply" button state and visual cues for staged changes)
- [ ] Task: Update Button Mapping Tab (Modify slots to stage changes instead of applying immediately)
- [ ] Task: Implement "Apply" and "Discard" UI Elements (Add buttons and link them to the transaction controller)
- [ ] Task: Integrate Transaction Logging into UI (Ensure batch results are visible in the expert console)
- [ ] Task: Conductor - User Manual Verification 'Phase 2: UI Refactor' (Protocol in workflow.md)

## Phase 3: Robustness & Final Polish
Goal: Ensure high reliability and finalize the user experience.

- [ ] Task: Write Tests for Error Recovery (Verify that interrupted batch writes can be recovered or safely aborted)
- [ ] Task: Final UX Pass (Polish button labels, tooltips, and overall flow for the staged remapping)
- [ ] Task: Conductor - User Manual Verification 'Phase 3: Robustness' (Protocol in workflow.md)
