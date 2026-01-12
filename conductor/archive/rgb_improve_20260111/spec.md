# Track Spec: Improve RGB Functionality

## Overview
The current RGB functionality in the Venus Pro configuration utility is incomplete and inaccurate. Selecting colors often results in incorrect output (e.g., magenta/pink), and the system lacks robust support for the device's native color presets. This track aims to reverse-engineer the correct RGB protocol using provided packet captures (`.pcapng` files) and implement a reliable, feature-rich RGB control tab.

## Functional Requirements
*   **Protocol Analysis:** Analyze the provided pcap files to decode the exact byte structure for RGB commands. Specifically, extract the 27 "Quick Pick" preset values to reverse-engineer the color encoding formula.
*   **Arbitrary Color Selection:** Implement a general-purpose color picker that uses the reverse-engineered formula to allow users to set *any* valid RGB color, not just the 27 presets.
*   **Standard Presets:** Implement the 27 "Quick Pick" steady colors as a quick-access palette to ensure 1:1 parity with the official driver's baseline.
*   **Mode Support:** Correctly implement and verify "Steady", "Breathing" (Respiration), and "Neon" modes.
*   **Brightness Control:** Ensure brightness adjustments work correctly across all modes.

## Non-Functional Requirements
*   **Protocol Compliance:** The implementation must strictly adhere to the reverse-engineered protocol to prevent device instability.
*   **Usability:** The RGB tab should present the 27 presets clearly (e.g., a grid of color swatches) alongside the custom picker.

## Out of Scope
*   Per-zone lighting (unless the protocol analysis reveals the device supports it, which is currently believed to be single-zone).
*   Audio-reactive lighting modes.
