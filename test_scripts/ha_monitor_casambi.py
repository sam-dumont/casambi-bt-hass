"""
Home Assistant Python Script to Monitor Casambi Connection via ESPHome Proxy.

Installation:
1. Copy this file to: /config/python_scripts/monitor_casambi.py
2. Enable python_script in configuration.yaml:
   python_script:
3. Restart Home Assistant
4. Call from Developer Tools > Services:
   Service: python_script.monitor_casambi
   Data:
     mac_address: "82:0A:EE:20:63:96"
     network_password: "your-password"
     duration: 300
     interval: 30

This script uses Home Assistant's Bluetooth manager to connect via ESPHome proxy,
exactly like the Casambi integration does.
"""

import asyncio
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

# Get parameters
mac_address = data.get("mac_address")
network_password = data.get("network_password")
duration = data.get("duration", 300)  # Default 5 minutes
interval = data.get("interval", 30)  # Default 30 seconds

if not mac_address or not network_password:
    logger.error("mac_address and network_password are required")
    raise ValueError("mac_address and network_password are required")

logger.info("=" * 60)
logger.info("Casambi ESPHome Proxy Connection Monitor")
logger.info("=" * 60)
logger.info(f"MAC Address: {mac_address}")
logger.info(f"Duration: {duration}s")
logger.info(f"Check Interval: {interval}s")
logger.info("=" * 60)

# Get Home Assistant Bluetooth manager
from homeassistant.components import bluetooth

# Get cache directory
from homeassistant.helpers.storage import STORAGE_DIR
cache_path = hass.config.path(STORAGE_DIR, "casambi_bt")

# Import Casambi library
try:
    from httpx import AsyncClient
    from CasambiBt import Casambi
except ImportError as e:
    logger.error(f"Failed to import Casambi library: {e}")
    logger.error("Make sure casambi-bt is installed in Home Assistant")
    raise

# Track stats
stats = {
    "connect_count": 0,
    "disconnect_count": 0,
    "start_time": None,
    "last_disconnect": None,
}

def disconnect_callback():
    """Called when device disconnects."""
    stats["disconnect_count"] += 1
    stats["last_disconnect"] = datetime.now()
    elapsed = (stats["last_disconnect"] - stats["start_time"]).total_seconds() if stats["start_time"] else 0
    logger.warning(f"🔴 DISCONNECT #{stats['disconnect_count']} (after {elapsed:.1f}s)")

async def monitor_connection():
    """Monitor the connection."""

    # Create HTTP client and Casambi instance
    http_client = AsyncClient()
    casa = Casambi(http_client, cache_path)

    # Register disconnect callback
    casa.registerDisconnectCallback(disconnect_callback)

    try:
        # Get BLE device from Home Assistant's Bluetooth manager
        logger.info("Getting device from Home Assistant Bluetooth manager...")
        device = bluetooth.async_ble_device_from_address(hass, mac_address, connectable=True)

        if not device:
            logger.error(f"Device {mac_address} not found in Home Assistant Bluetooth")
            logger.error("Make sure:")
            logger.error("  1. ESPHome Bluetooth proxy can see the device")
            logger.error("  2. Device is advertising")
            logger.error("  3. MAC address is correct")
            return

        logger.info(f"Found device via: {device.details.get('source', 'unknown')}")
        logger.info(f"Device name: {device.name}")
        logger.info(f"RSSI: {device.rssi}")

        # Connect
        logger.info("🔵 Connecting...")
        await casa.connect(device, network_password)

        if casa.connected:
            stats["connect_count"] += 1
            stats["start_time"] = datetime.now()
            logger.info("✅ CONNECTED")
            logger.info(f"   Network: {casa.networkName}")
            if hasattr(casa, '_casaNetwork') and hasattr(casa._casaNetwork, '_protocolVersion'):
                logger.info(f"   Protocol: {casa._casaNetwork._protocolVersion}")
        else:
            logger.error("❌ Connection failed")
            return

        # Monitor loop
        start = datetime.now()
        next_check = start.timestamp() + interval

        while (datetime.now() - start).total_seconds() < duration:
            await asyncio.sleep(1)

            now = datetime.now().timestamp()
            if now < next_check:
                continue

            next_check = now + interval

            # Check if still connected
            if casa.connected:
                elapsed = (datetime.now() - start).total_seconds()
                logger.info(f"✓ Still connected ({elapsed:.0f}s elapsed)")
            else:
                logger.warning("Connection lost. Attempting reconnect...")

                # Try to reconnect
                device = bluetooth.async_ble_device_from_address(hass, mac_address, connectable=True)
                if device:
                    try:
                        logger.info("🔄 Reconnecting...")
                        await casa.disconnect()
                        await asyncio.sleep(2)
                        await casa.connect(device, network_password)

                        if casa.connected:
                            stats["connect_count"] += 1
                            logger.info(f"✅ RECONNECTED (#{stats['connect_count']})")
                        else:
                            logger.error("❌ Reconnect failed")
                    except Exception as e:
                        logger.error(f"❌ Reconnect exception: {e}")
                        import traceback
                        logger.error(traceback.format_exc())
                else:
                    logger.error("Device not available for reconnect")

        logger.info("=" * 60)
        logger.info("MONITORING COMPLETE")
        logger.info("=" * 60)
        logger.info(f"Total connections: {stats['connect_count']}")
        logger.info(f"Total disconnects: {stats['disconnect_count']}")

        if stats["start_time"]:
            total_time = (datetime.now() - stats["start_time"]).total_seconds()
            logger.info(f"Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")

            if stats["disconnect_count"] > 0:
                mtbf = total_time / stats["disconnect_count"]
                logger.info(f"Avg time between disconnects: {mtbf:.1f}s ({mtbf/60:.1f} minutes)")

        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error in monitor: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        # Cleanup
        if casa.connected:
            await casa.disconnect()
        await http_client.aclose()

# Run the monitor
await monitor_connection()
