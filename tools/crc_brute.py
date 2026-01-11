from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import glob

def calculate_crc8(data, poly, init=0x00, xor_out=0x00, refin=False, refout=False):
    crc = init
    for byte in data:
        if refin:
            byte = int('{:08b}'.format(byte)[::-1], 2)
        crc ^= byte
        for _ in range(8):
            if crc & 0x80:
                crc = (crc << 1) ^ poly
            else:
                crc <<= 1
            crc &= 0xFF
    if refout:
        crc = int('{:08b}'.format(crc)[::-1], 2)
    return crc ^ xor_out

def solve_crc():
    # Load samples
    samples = []
    # 123 (Page 3)
    # File: artifacts/bin/extract_123_03_innerE8.bin
    # Data is in file
    
    files = glob.glob("extract_*.bin")
    for f in files:
        if "inner" not in f: continue
        try:
            target = int(f.split('inner')[1][:2], 16)
            with open(f, 'rb') as fh: data = fh.read()
            samples.append({'data': data, 'target': target, 'name': f})
        except: pass
        
    print(f"Loaded {len(samples)} samples.")
    
    # Brute force Poly and Init
    # XorOut is usually 0 or FF.
    
    possible_matches = []
    
    print("Testing Standard CRC8 (RefIn=False, RefOut=False)...")
    for poly in range(256):
        for init in range(256):
            match = True
            for s in samples:
                # We test on s['data'] (which excludes terminator)
                # But maybe checksum includes terminator header 00 03?
                # Data in file: [Valid Data]
                # Actual packet: [Valid Data] [00 03] [Inner(Target)]
                # Checksum usually covers [Valid Data] + [00 03]
                
                test_data = s['data'] + b'\x00\x03'
                
                calc = calculate_crc8(test_data, poly, init)
                if calc != s['target']:
                    match = False
                    break
            
            if match:
                print(f"MATCH FOUND! Poly=0x{poly:02X} Init=0x{init:02X} (Std)")
                return

    print("Testing Reflected CRC8...")
    for poly in range(256):
        for init in range(256):
            match = True
            for s in samples:
                test_data = s['data'] + b'\x00\x03'
                calc = calculate_crc8(test_data, poly, init, 0, True, True)
                if calc != s['target']:
                    match = False
                    break
            if match:
                print(f"MATCH FOUND! Poly=0x{poly:02X} Init=0x{init:02X} (Reflected)")
                return

    print("Checking offsets (Sum based)...")
    # ... (Sum check logic omitted as previously done)
    print("No CRC match found.")

if __name__ == "__main__":
    solve_crc()
