import asyncio
import logging
import json
import time
from typing import Dict, List, Any
from pathlib import Path

from remote_admin import load_remote_devices, execute_remote, RemoteDevice

logger = logging.getLogger(__name__)

class RemoteAdminBridge:
    """
    Bridge between RemoteAdmin logic and the WebSocket server.
    Handles device status monitoring and command routing.
    """
    
    def __init__(self, websocket_broadcast_callback=None):
        self.broadcast = websocket_broadcast_callback
        self.device_status: Dict[str, Dict[str, Any]] = {}
        self._monitor_task = None
        self.is_running = False

    async def start(self):
        """Start the background monitoring task."""
        self.is_running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        logger.info("[RemoteBridge] Monitoring task started")

    async def stop(self):
        """Stop the background monitoring task."""
        self.is_running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("[RemoteBridge] Monitoring task stopped")

    async def _monitor_loop(self):
        """Periodically check connectivity for all registered devices."""
        while self.is_running:
            try:
                devices = load_remote_devices()
                for device in devices:
                    # Check connectivity (simple uptime command)
                    started = time.time()
                    result = execute_remote(device.name, "uptime", use_paramiko=False)
                    latency = int((time.time() - started) * 1000)
                    
                    status = {
                        "name": device.name,
                        "online": result["success"],
                        "latency_ms": latency if result["success"] else -1,
                        "last_check": time.time(),
                        "device_type": device.device_type,
                        "host": device.host
                    }
                    
                    # Only notify if status changed
                    old_status = self.device_status.get(device.name)
                    if not old_status or old_status["online"] != status["online"]:
                        logger.info(f"[RemoteBridge] Device {device.name} is now {'ONLINE' if status['online'] else 'OFFLINE'}")
                        if self.broadcast:
                            await self.broadcast({
                                "type": "remote_status",
                                "device": status
                            })
                    
                    self.device_status[device.name] = status
                
                # Wait before next check (e.g., 60 seconds)
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"[RemoteBridge] Monitor error: {e}")
                await asyncio.sleep(10)

    async def get_all_status(self) -> List[Dict[str, Any]]:
        """Return status of all devices."""
        return list(self.device_status.values())

    async def run_command(self, device_name: str, command: str) -> Dict[str, Any]:
        """Execute a command and return result."""
        result = execute_remote(device_name, command)
        return result

_bridge = None
async def get_remote_bridge(broadcast_callback=None):
    global _bridge
    if _bridge is None:
        _bridge = RemoteAdminBridge(broadcast_callback)
        await _bridge.start()
    return _bridge
