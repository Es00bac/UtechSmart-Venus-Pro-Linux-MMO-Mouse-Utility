from pathlib import Path
import sys

for _parent in Path(__file__).resolve().parents:
    if (_parent / "venus_protocol.py").exists():
        sys.path.insert(0, str(_parent))
        break


import re

def parse_log_samples():
    log_file = "artifacts/txt/host_mouse_communication.txt"
    with open(log_file, 'r') as f:
        lines = f.readlines()
        
    samples = []
    
    current_page = None
    current_data = bytearray([0] * 2048) # Buffer
    max_offset = 0
    capture_name = ""
    
    # State tracking
    collecting = False
    
    for line in lines:
        if line.startswith("["):
            capture_name = line.strip()
            continue
            
        if "--> H2M | WRITE" in line:
            # Parse hex
            parts = line.split('|')[2].strip().split()
            bytes_dat = [int(b, 16) for b in parts]
            
            # Check for CMD 07 header
            # 08 07 00 PAGE OFF LEN ...
            if bytes_dat[1] == 0x07:
                page = bytes_dat[3]
                offset = bytes_dat[4]
                length = bytes_dat[5]
                data = bytes_dat[6:6+length]
                
                # New Page Start?
                if page != current_page:
                    if collecting and max_offset > 0:
                        # Process previous chunk if it had a terminator?
                        pass 
                    current_page = page
                    current_data = bytearray([0] * 2048)
                    max_offset = 0
                    collecting = True
                
                # Copy data
                for i in range(len(data)):
                    current_data[offset + i] = data[i]
                if offset + length > max_offset:
                    max_offset = offset + length
                    
                # Check for Terminator in this chunk
                # Terminator is 00 03 XX 00 00 00
                # Usually 6 bytes length
                if length == 6 and data[0] == 0x00 and data[1] == 0x03:
                    inner = data[2]
                    
                    # Valid data is up to offset + 6
                    term_end = offset + 6
                    # Full data up to terminator
                    # Note: "FullSum" in brute force def was sum of all bytes *including* start of buffer?
                    # The extracted files started at offset 0.
                    # So we take current_data[0 : term_end]
                    
                    full_blob = current_data[0 : term_end]
                    
                    # Calculate attributes
                    s_sum = sum(full_blob) & 0xFF
                    
                    # Event Count is at 0x1F (31)
                    count = full_blob[0x1F] if len(full_blob) >= 32 else 0
                    
                    samples.append({
                        'page': page,
                        'inner': inner,
                        'sum': s_sum,
                        'count': count,
                        'len': len(full_blob),
                        'term_off': offset,
                        'capture': capture_name
                    })
                    
                    # Reset collecting? No, subsequent writes might overwrite, but usually we move to next macro
                    
    # Deduplicate
    unique_samples = {}
    for s in samples:
        key = (s['sum'], s['count'], s['len'])
        if key not in unique_samples:
            unique_samples[key] = s
            
    print(f"Found {len(samples)} samples, {len(unique_samples)} unique.")
    print(f"{'SUM':<4} | {'CNT':<4} | {'LEN':<4} | {'PAGE':<4} | {'INNER (TGT)':<12} | {'Diff(~S-T)'}")
    print("-" * 60)
    
    for k, s in unique_samples.items():
        inv_sum = (~s['sum']) & 0xFF
        diff = (inv_sum - s['inner']) & 0xFF
        print(f"{s['sum']:02X}   | {s['count']:02X}   | {s['len']:02X}   | {s['page']:02X}   | {s['inner']:02X}           | {diff:02X} ({diff})")

    return unique_samples

if __name__ == "__main__":
    parse_log_samples()
