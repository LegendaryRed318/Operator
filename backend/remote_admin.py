#!/usr/bin/env python3
"""
remote_admin.py - SSH-based remote administration for JARVIS.
Execute commands on remote devices via Tailscale SSH or paramiko.
"""

import os
import subprocess
import logging
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

try:
    import paramiko
    PARAMIKO_AVAILABLE = True
except ImportError:
    PARAMIKO_AVAILABLE = False

logger = logging.getLogger(__name__)

# Configuration file for remote devices
REMOTE_DEVICES_PATH = Path(__file__).parent / "remote_devices.json"


@dataclass
class RemoteDevice:
    name: str
    host: str  # Tailscale hostname or IP (e.g., "homelab", "nas.tailnet.ts.net")
    user: str
    auth_method: str = "key"  # "key" or "password"
    key_path: Optional[str] = None
    password: Optional[str] = None
    device_type: str = "linux"  # "linux", "windows", "nas", "server", "android"
    port: int = 22  # SSH port (default 22, Termux uses 8022)
    
    def to_dict(self):
        return {
            "name": self.name,
            "host": self.host,
            "user": self.user,
            "auth_method": self.auth_method,
            "key_path": self.key_path,
            "password": self.password,
            "device_type": self.device_type,
            "port": self.port,
        }
    
    @classmethod
    def from_dict(cls, data: dict):
        return cls(**data)


def load_remote_devices() -> list[RemoteDevice]:
    """Load configured remote devices."""
    if not REMOTE_DEVICES_PATH.exists():
        # Create default empty config
        save_remote_devices([])
        return []
    
    try:
        with open(REMOTE_DEVICES_PATH, "r") as f:
            data = json.load(f)
        return [RemoteDevice.from_dict(d) for d in data]
    except Exception as e:
        logger.error(f"[RemoteAdmin] Failed to load devices: {e}")
        return []


def save_remote_devices(devices: list[RemoteDevice]):
    """Save remote device configuration."""
    try:
        REMOTE_DEVICES_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(REMOTE_DEVICES_PATH, "w") as f:
            json.dump([d.to_dict() for d in devices], f, indent=2)
        return True
    except Exception as e:
        logger.error(f"[RemoteAdmin] Failed to save devices: {e}")
        return False


def add_remote_device(name: str, host: str, user: str, 
                       auth_method: str = "key",
                       key_path: Optional[str] = None,
                       password: Optional[str] = None,
                       device_type: str = "linux") -> bool:
    """Add a new remote device to configuration."""
    devices = load_remote_devices()
    
    # Check for duplicate name
    if any(d.name.lower() == name.lower() for d in devices):
        logger.warning(f"[RemoteAdmin] Device '{name}' already exists")
        return False
    
    device = RemoteDevice(
        name=name,
        host=host,
        user=user,
        auth_method=auth_method,
        key_path=key_path,
        password=password,
        device_type=device_type,
    )
    
    devices.append(device)
    return save_remote_devices(devices)


def execute_ssh_paramiko(device: RemoteDevice, command: str, timeout: int = 30) -> dict:
    """Execute command via SSH using paramiko."""
    if not PARAMIKO_AVAILABLE:
        return {
            "success": False,
            "output": "",
            "error": "paramiko not installed - run: pip install paramiko"
        }
    
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        
        connect_kwargs = {
            "hostname": device.host,
            "port": device.port,
            "username": device.user,
            "timeout": timeout,
        }
        
        if device.auth_method == "key" and device.key_path:
            connect_kwargs["key_filename"] = device.key_path
        elif device.auth_method == "password" and device.password:
            connect_kwargs["password"] = device.password
        
        client.connect(**connect_kwargs)
        
        stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
        output = stdout.read().decode("utf-8", errors="ignore")
        error = stderr.read().decode("utf-8", errors="ignore")
        
        exit_code = stdout.channel.recv_exit_status()
        
        client.close()
        
        return {
            "success": exit_code == 0,
            "output": output.strip(),
            "error": error.strip() if error else None,
            "exit_code": exit_code,
        }
        
    except Exception as e:
        logger.error(f"[RemoteAdmin] SSH error to {device.host}: {e}")
        return {
            "success": False,
            "output": "",
            "error": str(e),
        }


def execute_ssh_subprocess(device: RemoteDevice, command: str, timeout: int = 30) -> dict:
    """Execute command via SSH using subprocess (for Tailscale SSH)."""
    try:
        # Use Tailscale SSH if available, otherwise fallback to system ssh
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=10"]
        
        # Add port if not default 22
        if device.port != 22:
            ssh_cmd.extend(["-p", str(device.port)])
        
        if device.auth_method == "key" and device.key_path:
            ssh_cmd.extend(["-i", device.key_path])
        
        ssh_cmd.append(f"{device.user}@{device.host}")
        ssh_cmd.append(command)
        
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="ignore"
        )
        
        return {
            "success": result.returncode == 0,
            "output": result.stdout.strip(),
            "error": result.stderr.strip() if result.stderr else None,
            "exit_code": result.returncode,
        }
        
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "output": "",
            "error": f"Command timed out after {timeout}s",
        }
    except Exception as e:
        logger.error(f"[RemoteAdmin] Subprocess SSH error: {e}")
        return {
            "success": False,
            "output": "",
            "error": str(e),
        }


def execute_remote(device_name: str, command: str, use_paramiko: bool = False) -> dict:
    """
    Execute a command on a remote device.
    
    Args:
        device_name: Friendly name of the device (e.g., "homelab", "nas")
        command: Shell command to execute
        use_paramiko: Use paramiko instead of subprocess/ssh
    
    Returns:
        dict with success, output, error
    """
    devices = load_remote_devices()
    device = next((d for d in devices if d.name.lower() == device_name.lower()), None)
    
    if not device:
        # Try to find by partial match
        device = next((d for d in devices if device_name.lower() in d.name.lower()), None)
    
    if not device:
        available = [d.name for d in devices]
        return {
            "success": False,
            "output": "",
            "error": f"Device '{device_name}' not found. Available: {available}"
        }
    
    logger.info(f"[RemoteAdmin] Executing on {device.name} ({device.host}): {command[:50]}...")
    
    if use_paramiko and PARAMIKO_AVAILABLE:
        return execute_ssh_paramiko(device, command)
    else:
        return execute_ssh_subprocess(device, command)


# Predefined remote commands
def check_disk_space(device_name: str) -> str:
    """Check disk space on remote device."""
    result = execute_remote(device_name, "df -h /")
    
    if result["success"]:
        lines = result["output"].split("\n")
        if len(lines) >= 2:
            # Parse df output
            parts = lines[1].split()
            if len(parts) >= 5:
                size, used, available, percent, mount = parts[1], parts[2], parts[3], parts[4], parts[5]
                return f"Disk on {device_name}: {used} used of {size} ({percent}), {available} free."
        return f"Disk info from {device_name}:\n{result['output']}"
    else:
        return f"Failed to check disk on {device_name}: {result.get('error', 'Unknown error')}"


def check_memory(device_name: str) -> str:
    """Check memory usage on remote device."""
    result = execute_remote(device_name, "free -h")
    
    if result["success"]:
        lines = result["output"].split("\n")
        for line in lines:
            if "Mem:" in line:
                parts = line.split()
                if len(parts) >= 4:
                    total, used, free = parts[1], parts[2], parts[3]
                    return f"Memory on {device_name}: {used} used of {total}, with {free} free."
        return f"Memory info from {device_name}:\n{result['output']}"
    else:
        return f"Failed to check memory on {device_name}: {result.get('error', 'Unknown error')}"


def restart_device(device_name: str) -> str:
    """Restart a remote device."""
    result = execute_remote(device_name, "sudo reboot", timeout=5)
    
    # Note: reboot command doesn't return success since connection drops
    if "Connection reset" in str(result.get("error", "")) or result.get("exit_code") == 255:
        return f"Restart command sent to {device_name}. The device should be restarting now."
    elif result["success"]:
        return f"Restart command executed on {device_name}."
    else:
        return f"Failed to restart {device_name}: {result.get('error', 'Unknown error')}"


def get_system_uptime(device_name: str) -> str:
    """Get system uptime from remote device."""
    result = execute_remote(device_name, "uptime -p 2>/dev/null || uptime")
    
    if result["success"]:
        return f"{device_name} uptime: {result['output']}"
    else:
        return f"Failed to get uptime from {device_name}: {result.get('error', 'Unknown error')}"


def check_battery(device_name: str) -> str:
    """Check battery status on Android device via Termux."""
    # Try termux-battery-status if available
    result = execute_remote(device_name, "termux-battery-status 2>/dev/null || echo 'Not available'")
    
    if result["success"] and "percentage" in result["output"]:
        return f"Battery on {device_name}: {result['output']}"
    
    # Fallback to /sys filesystem
    result = execute_remote(device_name, "cat /sys/class/power_supply/battery/capacity 2>/dev/null || echo 'Unknown'")
    
    if result["success"] and result["output"].strip().isdigit():
        level = result["output"].strip()
        return f"Battery on {device_name}: {level}%"
    
    return f"Unable to check battery on {device_name}. Install Termux:API app for full battery stats."


# Common Android app package names
ANDROID_APPS = {
    # Social
    "whatsapp": "com.whatsapp",
    "instagram": "com.instagram.android",
    "tiktok": "com.zhiliaoapp.musically",
    "facebook": "com.facebook.katana",
    "twitter": "com.twitter.android",
    "x": "com.twitter.android",
    "snapchat": "com.snapchat.android",
    "snap": "com.snapchat.android",
    "discord": "com.discord",
    "telegram": "org.telegram.messenger",
    "linkedin": "com.linkedin.android",
    "reddit": "com.reddit.frontpage",
    "pinterest": "com.pinterest",
    
    # Entertainment
    "youtube": "com.google.android.youtube",
    "netflix": "com.netflix.mediaclient",
    "prime": "com.amazon.avod.thirdpartyclient",
    "amazon prime": "com.amazon.avod.thirdpartyclient",
    "prime video": "com.amazon.avod.thirdpartyclient",
    "spotify": "com.spotify.music",
    "twitch": "tv.twitch.android.app",
    "disney": "com.disney.disneyplus",
    "disney+": "com.disney.disneyplus",
    "hulu": "com.hulu.plus",
    "hbo": "com.hbo.hbonow",
    "max": "com.wbd.stream",
    "youtube music": "com.google.android.apps.youtube.music",
    "apple music": "com.apple.android.music",
    "soundcloud": "com.soundcloud.android",
    "tidal": "com.aspiro.tidal",
    
    # Games
    "cod": "com.activision.callofduty.shooter",
    "call of duty": "com.activision.callofduty.shooter",
    "cod mobile": "com.activision.callofduty.shooter",
    "pubg": "com.tencent.ig",
    "pubg mobile": "com.tencent.ig",
    "roblox": "com.roblox.client",
    "minecraft": "com.mojang.minecraftpe",
    "fortnite": "com.epicgames.fortnite",
    "genshin": "com.miHoYo.GenshinImpact",
    "genshin impact": "com.miHoYo.GenshinImpact",
    "among us": "com.innersloth.spacemafia",
    "candy crush": "com.king.candycrushsaga",
    "clash of clans": "com.supercell.clashofclans",
    "clash royale": "com.supercell.clashroyale",
    "pokemon go": "com.nianticlabs.pokemongo",
    
    # Productivity
    "chrome": "com.android.chrome",
    "gmail": "com.google.android.gm",
    "maps": "com.google.android.apps.maps",
    "google maps": "com.google.android.apps.maps",
    "calendar": "com.google.android.calendar",
    "photos": "com.google.android.apps.photos",
    "drive": "com.google.android.apps.docs",
    "docs": "com.google.android.apps.docs.editors.docs",
    "sheets": "com.google.android.apps.docs.editors.sheets",
    "slides": "com.google.android.apps.docs.editors.slides",
    "keep": "com.google.android.keep",
    "translate": "com.google.android.apps.translate",
    "clock": "com.google.android.deskclock",
    "calculator": "com.google.android.calculator",
    "settings": "com.android.settings",
    "files": "com.google.android.apps.nbu.files",
    "file manager": "com.google.android.apps.nbu.files",
    
    # Banking/Shopping
    "revolut": "com.revolut.revolut",
    "monzo": "co.uk.getmondo",
    "amazon": "com.amazon.mshop.android.shopping",
    "ebay": "com.ebay.mobile",
    "paypal": "com.paypal.android.p2pmobile",
    "deliveroo": "com.deliveroo.orderapp",
    "uber": "com.ubercab",
    "uber eats": "com.ubercab.eats",
    "just eat": "com.justeat.app.uk",
    "airbnb": "com.airbnb.android",
    
    # Communication
    "teams": "com.microsoft.teams",
    "zoom": "us.zoom.videomeetings",
    "meet": "com.google.android.apps.meetings",
    "google meet": "com.google.android.apps.meetings",
    "slack": "com.Slack",
    "skype": "com.skype.raider",
}


def open_android_app(device_name: str, app_name: str) -> str:
    """
    Open an Android app on remote device via Termux.
    
    Args:
        device_name: Name of configured device
        app_name: Friendly name of app (e.g., "whatsapp", "youtube")
    
    Returns:
        Success/failure message
    """
    # Normalize app name
    app_key = app_name.lower().strip()
    
    # Try exact match first
    package = ANDROID_APPS.get(app_key)
    
    # Try partial match
    if not package:
        for key, pkg in ANDROID_APPS.items():
            if app_key in key or key in app_key:
                package = pkg
                break
    
    if not package:
        available = list(ANDROID_APPS.keys())
        return f"App '{app_name}' not recognized. Available apps: {', '.join(available[:10])}..."
    
    # Try to open the app
    result = execute_remote(device_name, f"am start -n {package}/.MainActivity 2>&1 || am start -a android.intent.action.MAIN -n {package}/.Launcher")
    
    if result["success"] or "Starting" in result.get("output", "") or "Warning" in result.get("output", ""):
        return f"Opening {app_name} on {device_name}."
    else:
        # Try alternative launch method
        result2 = execute_remote(device_name, f"monkey -p {package} -c android.intent.category.LAUNCHER 1")
        if result2["success"]:
            return f"Opening {app_name} on {device_name}."
        
        return f"Could not open {app_name} on {device_name}. Error: {result.get('error', 'Unknown error')}"


def close_android_app(device_name: str, app_name: str) -> str:
    """
    Close (force-stop) an Android app on remote device.
    
    Args:
        device_name: Name of configured device
        app_name: Friendly name of app
    
    Returns:
        Success/failure message
    """
    # Normalize app name
    app_key = app_name.lower().strip()
    package = ANDROID_APPS.get(app_key)
    
    # Try partial match
    if not package:
        for key, pkg in ANDROID_APPS.items():
            if app_key in key or key in app_key:
                package = pkg
                break
    
    if not package:
        return f"App '{app_name}' not recognized. Cannot close it."
    
    # Force stop the app
    result = execute_remote(device_name, f"am force-stop {package}")
    
    if result["success"]:
        return f"Closed {app_name} on {device_name}."
    else:
        return f"Could not close {app_name}. It may not be running or you need root access."


def control_media(device_name: str, action: str) -> str:
    """
    Control media playback on Android device.
    
    Args:
        device_name: Name of configured device
        action: "play", "pause", "stop", "next", "previous", "volume_up", "volume_down"
    
    Returns:
        Success/failure message
    """
    action = action.lower().strip()
    
    # Media key codes
    key_codes = {
        "play": 126,
        "pause": 127,
        "play_pause": 85,
        "stop": 86,
        "next": 87,
        "skip": 87,
        "previous": 88,
        "prev": 88,
        "volume_up": 24,
        "volume_down": 25,
        "mute": 164,
    }
    
    if action not in key_codes:
        return f"Unknown media action '{action}'. Try: play, pause, next, previous, volume_up, volume_down"
    
    key_code = key_codes[action]
    result = execute_remote(device_name, f"input keyevent {key_code}")
    
    if result["success"]:
        action_past = {
            "play": "Playing",
            "pause": "Paused",
            "stop": "Stopped",
            "next": "Skipped to next",
            "skip": "Skipped to next",
            "previous": "Went to previous",
            "prev": "Went to previous",
            "volume_up": "Volume up",
            "volume_down": "Volume down",
            "mute": "Muted",
        }
        return f"{action_past.get(action, action)} on {device_name}."
    else:
        return f"Could not control media on {device_name}."


def take_screenshot(device_name: str, save_path: Optional[str] = None) -> str:
    """
    Take a screenshot on Android device.
    
    Args:
        device_name: Name of configured device
        save_path: Optional path to save screenshot (defaults to /sdcard/Download)
    
    Returns:
        Success/failure message with screenshot location
    """
    from datetime import datetime
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"jarvis_screenshot_{timestamp}.png"
    
    if save_path:
        filepath = f"{save_path}/{filename}"
    else:
        filepath = f"/sdcard/Download/{filename}"
    
    # Take screenshot using screencap
    result = execute_remote(device_name, f"screencap -p {filepath}")
    
    if result["success"]:
        return f"Screenshot taken on {device_name} and saved to {filepath}."
    else:
        # Try pulling to local if direct save fails
        return f"Screenshot attempt on {device_name} had issues. You may need to install Termux:API for full functionality."


def list_services(device_name: str, service_name: Optional[str] = None) -> str:
    """List or check status of services on remote device."""
    if service_name:
        cmd = f"systemctl status {service_name} --no-pager -l"
        result = execute_remote(device_name, cmd)
        
        if result["success"]:
            # Check if active
            if "Active: active" in result["output"]:
                return f"Service {service_name} on {device_name} is running."
            elif "Active: inactive" in result["output"]:
                return f"Service {service_name} on {device_name} is stopped."
            else:
                return f"Service {service_name} status on {device_name}:\n{result['output'][:500]}"
        else:
            return f"Failed to check {service_name} on {device_name}: {result.get('error', 'Unknown error')}"
    else:
        # List failed services
        result = execute_remote(device_name, "systemctl --failed --no-pager")
        
        if result["success"]:
            if "0 loaded units listed" in result["output"] or len(result["output"].strip()) < 50:
                return f"All services on {device_name} are running normally."
            else:
                return f"Failed services on {device_name}:\n{result['output'][:800]}"
        else:
            return f"Failed to list services on {device_name}: {result.get('error', 'Unknown error')}"


# Wake-on-LAN support
def wake_on_lan(mac_address: str, broadcast_ip: str = "255.255.255.255") -> str:
    """
    Send Wake-on-LAN magic packet to wake up a device.
    
    Args:
        mac_address: MAC address in format "AA:BB:CC:DD:EE:FF" or "AA-BB-CC-DD-EE-FF"
        broadcast_ip: Broadcast IP address
    """
    try:
        import socket
        import struct
        
        # Normalize MAC address
        mac = mac_address.replace(":", "").replace("-", "").replace(".", "")
        if len(mac) != 12:
            return f"Invalid MAC address format: {mac_address}"
        
        # Create magic packet: 6 bytes of 0xFF followed by 16 repetitions of MAC
        data = b"FF" * 6 + mac.encode() * 16
        packet = bytes.fromhex(data.decode())
        
        # Send packet
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.sendto(packet, (broadcast_ip, 9))  # Port 9 for WoL
        sock.close()
        
        logger.info(f"[RemoteAdmin] Wake-on-LAN packet sent to {mac_address}")
        return f"Wake-on-LAN packet sent to {mac_address}. The device should wake up shortly."
        
    except Exception as e:
        logger.error(f"[RemoteAdmin] Wake-on-LAN error: {e}")
        return f"Failed to send Wake-on-LAN packet: {e}"


if __name__ == "__main__":
    # Test/example usage
    print("Remote Admin module loaded.")
    print(f"Devices config: {REMOTE_DEVICES_PATH}")
    
    # Example: Add a device
    # add_remote_device("homelab", "homelab.tailnet.ts.net", "admin", device_type="server")
    
    # Example: Execute command
    # result = execute_remote("homelab", "uptime")
    # print(result)
