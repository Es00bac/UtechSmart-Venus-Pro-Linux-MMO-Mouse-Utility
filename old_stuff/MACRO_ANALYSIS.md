# Macro Format Analysis - Windows Working vs Linux Broken

## Summary of Key Differences

| Aspect | Windows (WORKING) | Linux (BROKEN) |
|--------|-------------------|----------------|
| Last event delay | `00 03` (3ms) | `00 23` (normal delay) |
| Terminator format | `[checksum] 00 00 00` | `03 [checksum] 00 00 00` |
| Terminator position | Immediately after last event | Has padding/garbage before |

## Detailed Analysis

### Working Macro: "ohshit" from artifacts/bin/ohshit.bin (Windows)

```
Header (0x300-0x31F):
  0x300: 0c                     = Name length (12 bytes = "ohshit")
  0x301-0x30C: 6f 00 68 00...   = "ohshit" UTF-16LE
  0x31F: 14                     = Event count (20 decimal)

Events (0x320-0x383): 20 events × 5 bytes = 100 bytes
  Event 1:  81 12 00 00 23  = O down, 35ms
  Event 2:  41 12 00 00 23  = O up, 35ms
  ...
  Event 19: 81 2c 00 00 23  = Space down, 35ms
  Event 20: 41 2c 00 00 03  = Space up, 3ms  <-- LAST EVENT HAS 3ms DELAY!

Terminator (0x384-0x387):
  45 00 00 00  = checksum 0x45, no 0x03 prefix!
```

### Broken Macro: "ohshit3" from artifacts/bin/linux_ohshit3.bin (Linux)

```
Header (0x300-0x31F):
  0x300: 0e                     = Name length (14 bytes = "ohshit3")
  0x301-0x30E: 6f 00 68 00...   = "ohshit3" UTF-16LE
  0x31F: 24                     = Event count (36 decimal) <-- WRONG? Only ~18 actual events?

Events (0x320-0x379):
  Event 1:  81 12 00 00 23  = O down, 35ms
  ...
  Event 18: 41 2c 00 00 23  = Space up, 35ms  <-- NOT 3ms!

Garbage/Padding (0x37A-0x383):
  00 00 00 00 00 00 00 00 00  = zeros (shouldn't be here!)

Wrong Terminator (0x383-0x387):
  03 82 00 00 00  = HAS 0x03 PREFIX - WRONG!
```

## Verified Pattern from Multiple Windows Macros

### "123" macro (18 events)
- Last event: `41 26 00 00 03` (9-up, 3ms delay)
- Terminator: `e8 00 00 00`

### "456" macro (12 events)
- Last event: `41 1f 00 00 03` (2-up, 3ms delay)
- Terminator: `38 00 00 00`

### "789" macro (8 events)
- Last event: `41 1f 00 00 03` (2-up, 3ms delay)
- Terminator: `8e 00 00 00`

### "ohshit" macro (20 events)
- Last event: `41 2c 00 00 03` (Space-up, 3ms delay)
- Terminator: `45 00 00 00`

## THE FIX

1. **Last event's delay bytes MUST be `00 03`** (3ms)
   - NOT the same delay as other events
   - This is a convention/marker, not a terminator

2. **Terminator is exactly 4 bytes: `[checksum] 00 00 00`**
   - NO `03` prefix
   - The `03` seen in dumps is the last event's delay

3. **Terminator immediately follows the last event**
   - No padding between events and terminator

## Event Format (5 bytes each)

```
[0] Type:     0x81 = key down, 0x41 = key up
              0x80 = modifier down, 0x40 = modifier up
[1] Scancode: HID scancode
[2] Reserved: 0x00 (always)
[3] Delay Hi: High byte of delay in ms
[4] Delay Lo: Low byte of delay (0x03 for last event!)
```
