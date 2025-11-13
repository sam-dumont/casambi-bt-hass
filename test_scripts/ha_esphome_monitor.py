#!/usr/bin/env python3
"""
Monitor Casambi connection using Home Assistant's Bluetooth manager and ESPHome proxy.

This script must be run ON the Home Assistant host (not remotely) to access
the Bluetooth manager and ESPHome proxy infrastructure.

Installation:
1. SSH into your Home Assistant host
2. Copy this script to /config/scripts/ha_esphome_monitor.py
3. Make it executable: chmod +x /config/scripts/ha_esphome_monitor.py
4. Run it: python3 /config/scripts/ha_esphome_monitor.py --mac 82:0A:EE:20:63:96 --password YOUR_PASSWORD

Requirements:
- Must run on Home Assistant host (has access to HA's Python environment)
- Casambi integration must be installed (has casambi-bt library)
"""

import asyncio
import sys
import logging
import argparse
import getpass
from datetime import datetime
from pathlib import Path

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Suppress verbose logs
logging.getLogger("bleak").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)

# Check if we're running in Home Assistant environment
try:
    # These paths indicate we're on a Home Assistant installation
    HA_PATHS = [
        Path("/config"),
        Path("/usr/src/homeassistant"),
    ]
    is_ha_host = any(p.exists() for p in HA_PATHS)

    if not is_ha_host:
        logger.error("=" * 60)
        logger.error("ERROR: This script must run ON the Home Assistant host!")
        logger.error("=" * 60)
        logger.error("This script needs access to Home Assistant's Bluetooth manager")
        logger.error("and ESPHome proxy infrastructure.")
        logger.error("")
        logger.error("To run this script:")
        logger.error("1. SSH into your Home Assistant host")
        logger.error("2. Copy this script to /config/scripts/")
        logger.error("3. Run: python3 /config/scripts/ha_esphome_monitor.py [options]")
        logger.error("=" * 60)
        sys.exit(1)

except Exception as e:
    logger.warning(f"Could not verify HA environment: {e}")

# Try to import Home Assistant modules
try:
    # Add HA to path if needed
    ha_paths = [
        "/usr/src/homeassistant/homeassistant",
        "/usr/local/lib/python3.13/site-packages",
    ]
    for p in ha_paths:
        if Path(p).exists() and p not in sys.path:
            sys.path.insert(0, str(Path(p).parent))

    # Import HA components - these will only work on HA host
    from homeassistant.core import HomeAssistant
    from homeassistant.components import bluetooth

except ImportError as e:
    logger.error(f"Failed to import Home Assistant modules: {e}")
    logger.error("Make sure you're running this ON the Home Assistant host")
    sys.exit(1)

# Import Casambi library
try:
    from httpx import AsyncClient
    from CasambiBt import Casambi
except ImportError as e:
    logger.error(f"Failed to import Casambi library: {e}")
    logger.error("Install with: pip3 install CasambiBt")
    sys.exit(1)


class HAESPHomeMonitor:
    """Monitor Casambi connection via HA's Bluetooth/ESPHome infrastructure."""

    def __init__(self, hass, mac_address, network_password, cache_path):
        self.hass = hass
        self.mac_address = mac_address
        self.network_password = network_password
        self.cache_path = cache_path

        self.casa = None
        self.http_client = None

        self.connect_count = 0
        self.disconnect_count = 0
        self.reconnect_success = 0
        self.reconnect_failures = 0

        self.start_time = None
        self.last_disconnect_time = None

    def _disconnect_callback(self):
        """Called when device disconnects."""
        self.disconnect_count += 1
        self.last_disconnect_time = datetime.now()

        elapsed = (self.last_disconnect_time - self.start_time).total_seconds() if self.start_time else 0
        logger.warning(f"🔴 DISCONNECT #{self.disconnect_count} (after {elapsed:.1f}s)")

    async def connect(self):
        """Connect to Casambi device via HA Bluetooth manager."""
        try:
            logger.info(f"🔵 CONNECT ATTEMPT #{self.connect_count + 1}")

            # Create HTTP client if needed
            if not self.http_client:
                self.http_client = AsyncClient()

            # Create Casambi instance if needed
            if not self.casa:
                self.casa = Casambi(self.http_client, self.cache_path)

            # Register disconnect callback
            self.casa.registerDisconnectCallback(self._disconnect_callback)

            # Get device from HA's Bluetooth manager
            logger.info("Getting device from Home Assistant Bluetooth manager...")
            device = bluetooth.async_ble_device_from_address(
                self.hass,
                self.mac_address,
                connectable=True
            )

            if not device:
                logger.error(f"❌ Device {self.mac_address} not found in HA Bluetooth")
                logger.error("   Make sure ESPHome proxy can see the device")
                return False

            # Log device details
            source = device.details.get('source', 'unknown')
            logger.info(f"✓ Found device: {device.name}")
            logger.info(f"  Source: {source}")
            logger.info(f"  RSSI: {device.rssi}")

            # If using ESPHome proxy, log which one
            if 'esp' in source.lower():
                logger.info(f"  📡 Using ESPHome proxy: {source}")

            # Connect
            logger.info("Connecting to device...")
            await self.casa.connect(device, self.network_password)

            if self.casa.connected:
                self.connect_count += 1
                if not self.start_time:
                    self.start_time = datetime.now()
                logger.info(f"✅ CONNECTED (#{self.connect_count})")
                logger.info(f"   Network: {self.casa.networkName}")
                if hasattr(self.casa, '_casaNetwork') and hasattr(self.casa._casaNetwork, '_protocolVersion'):
                    logger.info(f"   Protocol: {self.casa._casaNetwork._protocolVersion}")
                return True
            else:
                logger.error("❌ Connection failed - casa.connected is False")
                return False

        except Exception as e:
            logger.error(f"❌ CONNECTION FAILED: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def reconnect(self):
        """Attempt to reconnect."""
        logger.info("🔄 RECONNECT ATTEMPT...")

        try:
            # Disconnect cleanly first
            if self.casa and self.casa.connected:
                try:
                    await self.casa.disconnect()
                except Exception as e:
                    logger.debug(f"Disconnect error (ignoring): {e}")
                await asyncio.sleep(2)

            # Try to reconnect
            success = await self.connect()

            if success:
                self.reconnect_success += 1
                logger.info(f"✅ RECONNECT SUCCESS (#{self.reconnect_success})")
                return True
            else:
                self.reconnect_failures += 1
                logger.error(f"❌ RECONNECT FAILED (#{self.reconnect_failures})")
                return False

        except Exception as e:
            self.reconnect_failures += 1
            logger.error(f"❌ RECONNECT EXCEPTION: {type(e).__name__}: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return False

    async def monitor(self, duration_seconds=None, check_interval=30):
        """Monitor the connection for a specified duration."""
        logger.info("=" * 60)
        logger.info("Starting HA ESPHome Proxy Connection Monitor...")
        logger.info("=" * 60)

        # Connect initially
        if not await self.connect():
            logger.error("Initial connection failed. Exiting.")
            return

        start = datetime.now()
        next_check = start.timestamp() + check_interval

        try:
            while True:
                # Check if duration exceeded
                if duration_seconds:
                    elapsed = (datetime.now() - start).total_seconds()
                    if elapsed >= duration_seconds:
                        logger.info("Monitoring duration completed.")
                        break

                # Wait until next check time
                await asyncio.sleep(1)
                now = datetime.now().timestamp()
                if now < next_check:
                    continue

                next_check = now + check_interval

                # Check if still connected
                if self.casa.connected:
                    elapsed = datetime.now().timestamp() - start.timestamp()
                    logger.info(f"✓ Still connected ({elapsed:.0f}s elapsed)")
                else:
                    # Lost connection, try to reconnect
                    logger.warning("Connection lost. Attempting reconnect...")
                    await self.reconnect()

        except KeyboardInterrupt:
            logger.info("\nStopping monitor...")
            raise

        finally:
            # Print summary
            self.print_summary()

            # Cleanup
            if self.casa and self.casa.connected:
                await self.casa.disconnect()
            if self.http_client:
                await self.http_client.aclose()

    def print_summary(self):
        """Print monitoring summary."""
        logger.info("=" * 60)
        logger.info("MONITORING SUMMARY")
        logger.info("=" * 60)
        print(f"Total connection attempts: {self.connect_count}")
        print(f"Total disconnects: {self.disconnect_count}")
        print(f"Reconnect successes: {self.reconnect_success}")
        print(f"Reconnect failures: {self.reconnect_failures}")

        if self.start_time:
            total_time = (datetime.now() - self.start_time).total_seconds()
            print(f"Total monitoring time: {total_time:.1f}s ({total_time/60:.1f} minutes)")

            if self.disconnect_count > 0:
                mtbf = total_time / self.disconnect_count
                print(f"Avg time between disconnects: {mtbf:.1f}s ({mtbf/60:.1f} minutes)")
        print("=" * 60)


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Monitor Casambi via Home Assistant's ESPHome Bluetooth Proxy"
    )
    parser.add_argument("--mac", type=str, required=True,
                       help="Casambi device MAC address")
    parser.add_argument("--password", type=str,
                       help="Casambi network password (will prompt if not provided)")
    parser.add_argument("--duration", type=int,
                       help="Monitoring duration in seconds (omit for indefinite)")
    parser.add_argument("--interval", type=int, default=30,
                       help="Check interval in seconds (default: 30)")
    parser.add_argument("--cache", type=str, default="/config/.storage/casambi_bt",
                       help="Cache directory for Casambi data")

    args = parser.parse_args()

    # Get password if not provided
    network_password = args.password or getpass.getpass("Enter Casambi network password: ")

    # Ensure cache directory exists
    cache_path = Path(args.cache)
    cache_path.mkdir(parents=True, exist_ok=True)

    # Create a minimal Home Assistant instance
    # Note: This is a simplified version - full HA has more setup
    logger.info("Initializing Home Assistant instance...")
    hass = HomeAssistant("/config")

    # TODO: Full HA initialization would include:
    # - await hass.async_start()
    # - Loading bluetooth component
    # - Setting up ESPHome integrations
    # This is complex and may require running as a proper HA script

    logger.info("=" * 60)
    logger.info("Home Assistant ESPHome Proxy Monitor")
    logger.info("=" * 60)
    logger.info(f"Device MAC: {args.mac}")
    logger.info(f"Check interval: {args.interval}s")
    logger.info(f"Duration: {'Indefinite (Ctrl+C to stop)' if not args.duration else f'{args.duration}s'}")
    logger.info("=" * 60)

    # Create monitor
    monitor = HAESPHomeMonitor(
        hass=hass,
        mac_address=args.mac,
        network_password=network_password,
        cache_path=str(cache_path)
    )

    # Start monitoring
    await monitor.monitor(
        duration_seconds=args.duration,
        check_interval=args.interval
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
        sys.exit(0)
