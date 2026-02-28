"""Device detection and factory layer.

Provides a thin abstraction to detect which device variant is connected
and create the appropriate device/protocol objects.
"""
from __future__ import annotations

import venus_protocol as vp
import holtek_protocol as hp


def detect_device_type(device_info: vp.DeviceInfo) -> str:
    """Determine device type from VID/PID.

    Returns 'holtek' for 04D9:FC55, 'venus_pro' otherwise.
    """
    if device_info.vendor_id == hp.VENDOR_ID and device_info.product_id == hp.PRODUCT_ID:
        return 'holtek'
    return 'venus_pro'


def get_button_profiles(device_type: str) -> dict:
    """Return the appropriate BUTTON_PROFILES dict for the device type."""
    if device_type == 'holtek':
        return hp.BUTTON_PROFILES
    return vp.BUTTON_PROFILES


def create_device(device_type: str, path: str):
    """Factory: create the right device class for the variant.

    Returns HoltekDevice or VenusDevice.
    """
    if device_type == 'holtek':
        return hp.HoltekDevice(path)
    return vp.VenusDevice(path)
