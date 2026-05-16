#!/usr/bin/env python3
from backend.remote_admin import load_remote_devices, save_remote_devices

devices = load_remote_devices()
samsung = next((d for d in devices if d.name == 'samsung'), None)

if samsung:
    samsung.port = 8022
    samsung.device_type = 'android'
    save_remote_devices(devices)
    print(f"Updated samsung device: port={samsung.port}, device_type={samsung.device_type}")
else:
    print("Samsung device not found")
