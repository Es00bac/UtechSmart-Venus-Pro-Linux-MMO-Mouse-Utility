import hid
import venus_protocol as vp

print("Enumerating devices...")
found = []
for d in hid.enumerate(vp.VENDOR_ID, 0):
    if d['product_id'] in vp.PRODUCT_IDS:
        print(f"Found: {d['product_string']} (PID {d['product_id']:04x}) Interface: {d['interface_number']} Path: {d['path']}")
        found.append(d)

print("\nvenus_protocol.list_devices() output:")
devices = vp.list_devices()
for d in devices:
    print(f"  {d.product} - {d.path}")

print("\nAnalysis:")
if len(devices) > len([f for f in found if f['interface_number'] == 1]):
    print("WARNING: venus_protocol is returning non-config interfaces!")
else:
    print("venus_protocol seems to be filtering correctly (or only 1 interface exists).")
