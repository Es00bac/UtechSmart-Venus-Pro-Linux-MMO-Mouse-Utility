from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import glob
import os
import sys

class Colors:
    OKGREEN = '\033[92m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'

def calculate_checksums(data):
    """Generates a dictionary of potential checksum names and values."""
    checksums = {}
    
    # Smart Slice based on Event Count (Byte 0x1F)
    valid_data = data
    if len(data) >= 0x20:
        count = data[0x1F]
        # Length = 32 header + (count * 5) bytes
        # Note: Last event's last 2 bytes might be missing in 'data' if extracted up to terminator
        expected_len = 0x20 + (count * 5)
        
        # We process 'data' as is, but we also try to pad it if it looks short
        # relative to expected_len
        
        # Slices
        slices = {'full': data}
        
        # Exact length slice (if data has garbage at end)
        if len(data) >= expected_len:
            slices['exact'] = data[:expected_len]
        # Truncated (up to terminataor) - this is 'data' already usually
        
        # Events only
        if len(data) > 0x20:
            slices['events'] = data[0x20:]
            
        # Process each slice
        for sname, sdata in slices.items():
            # Sums
            s = sum(sdata)
            checksums[f'{sname}_sum'] = s & 0xFF
            checksums[f'{sname}_0x55_minus_sum'] = (0x55 - s) & 0xFF
            
            # XOR
            x = 0
            for b in sdata: x ^= b
            checksums[f'{sname}_xor'] = x
            
            # CRC8
            c = 0
            for b in sdata:
                c ^= b
                for _ in range(8):
                    if c & 0x80: c = (c << 1) ^ 0x07
                    else: c = (c << 1)
                c &= 0xFF
            checksums[f'{sname}_crc8_07'] = c
            
            # Try to find a constant offset
            # offset = (Target - Sum)
            # We can't store offset here, but we iterate later
            
            # Testing special pattern: "Sum of bytes / 4"
            checksums[f'{sname}_sum_div_4'] = (s // 4) & 0xFF
            
            # "Sum of shorts"
            if len(sdata) % 2 == 0:
                ss = 0
                for i in range(0, len(sdata), 2):
                    ss += (sdata[i] | (sdata[i+1] << 8))
                checksums[f'{sname}_sum16'] = ss & 0xFF
                checksums[f'{sname}_xor16'] = (ss >> 8) & 0xFF

    return checksums

def solve_linear_combinations(samples):
    print(f"\n{Colors.OKGREEN}Searching for Linear Combinations (A*Sum + B*Count + K)...{Colors.ENDC}")
    
    # We want: (A*Sum + B*Count + K) & 0xFF == Target
    # Iterate A, B, K in range -5 to 5 (and K 0..255)
    
    points = []
    for s in samples:
        # Extract variables
        full_sum = s['candidates']['full_sum']
        ev_sum = s['candidates'].get('events_sum', 0)
        
        # Count is at 0x1F if len >= 32
        count = 0
        if len(s['data']) >= 0x20:
            count = s['data'][0x1F]
            
        points.append({
            'name': s['name'],
            'target': s['target'],
            'vars': {
                'FullSum': full_sum,
                'EvSum': ev_sum,
                'Count': count,
                'Len': len(s['data'])
            }
        })
        
    # Variables to test
    var_names = ['FullSum', 'EvSum', 'Count', 'Len']
    
    found = False
    
    # Simple form: Target = (Factor * Var) + K
    for vname in var_names:
        for factor in [1, -1]:
            # Calculate required K for each sample
            ks = []
            for p in points:
                # K = Target - (Factor * Val)
                val = p['vars'][vname]
                k = (p['target'] - (factor * val)) & 0xFF
                ks.append(k)
            
            if len(set(ks)) == 1:
                k = ks[0]
                sign = "+" if factor == 1 else "-"
                print(f"  [MATCH] Target = ({sign}{vname} + 0x{k:02X}) & 0xFF")
                found = True

    # Bi-variable form: Target = (V1 + V2 + K) or (V1 - V2 + K) etc
    # Let's try (Sum + Count + K)
    import itertools
    for v1, v2 in itertools.combinations(var_names, 2):
        for f1 in [1, -1]:
            for f2 in [1, -1]:
                ks = []
                for p in points:
                    val1 = p['vars'][v1]
                    val2 = p['vars'][v2]
                    # Target = f1*v1 + f2*v2 + K
                    # K = Target - f1*v1 - f2*v2
                    k = (p['target'] - (f1*val1) - (f2*val2)) & 0xFF
                    ks.append(k)
                    
                if len(set(ks)) == 1:
                    k = ks[0]
                    s1 = "+" if f1==1 else "-"
                    s2 = "+" if f2==1 else "-"
                    print(f"  [MATCH] Target = ({s1}{v1} {s2}{v2} + 0x{k:02X}) & 0xFF")
                    found = True
                    
    if not found:
        print("  No simple linear combination found.")
        # Print table for manual inspection
        print(f"\n{'Name':<20} | {'TGT':<4} | {'FullS':<5} | {'EvSum':<5} | {'Cnt':<3} | {'Len':<3}")
        print("-" * 60)
        for p in points:
            print(f"{p['name'][:20]:<20} | {p['target']:02X}   | {p['vars']['FullSum']:02X}    | {p['vars']['EvSum']:02X}    | {p['vars']['Count']:02X}  | {p['vars']['Len']:02X}")

def brute_force():
    files = glob.glob("extract_*.bin")
    samples = []
    
    # Load extracted binaries
    print(f"DEBUG: Found {len(files)} files via glob")
    for f in files:
        parts = f.replace('.bin','').split('_')
        try:
            # Handle standard naming "extract_NAME_PAGE_innerXX.bin"
            # or manual "extract_unk_PAGE_PAGE_innerXX.bin"
            if 'inner' in parts[-1]:
                inner_hex = parts[-1].replace('inner', '')
                target = int(inner_hex, 16)
            else:
                continue
        except: continue
        
        with open(f, 'rb') as fh: raw = fh.read()
        samples.append({
            'name': f,
            'data': raw,
            'target': target,
            'candidates': calculate_checksums(raw)
        })

    if os.path.exists("artifacts/bin/ohshit.bin"):
        with open("artifacts/bin/ohshit.bin", "rb") as f:
            full = f.read()
            # 0x03 Ohshit data
            data = full[0x300:0x382]
            samples.append({
                'name': 'manual_ohshit',
                'data': data,
                'target': 0x45,
                'candidates': calculate_checksums(data)
            })
            
    if samples:
        solve_linear_combinations(samples)

if __name__ == "__main__":
    brute_force()
