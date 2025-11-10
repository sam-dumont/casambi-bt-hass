#!/usr/bin/env python3
"""
Monitor Casambi BT connection and verify ESPHome Bluetooth Proxy can see the device.

This script:
1. Verifies ESPHome proxy can see the device (validates proxy is working)
2. Uses direct Bleak connection for monitoring (same as HA integration does)
3. Helps debug connection stability issues
"""

import asyncio
import logging
import sys
import getpass
import time
from datetime import datetime
from pathlib import Path

try:
    from httpx import AsyncClient
except ImportError:
    print("ERROR: httpx not installed. Install with: pip install httpx")
    sys.exit(1)

try:
    from aioesphomeapi import APIClient, BluetoothProxyFeature
except ImportError:
    print("ERROR: aioesphomeapi not installed.")
    print("Install with: pip install aioesphomeapi")
    sys.exit(1)

try:
    from bleak import BleakScanner
except ImportError:
    print("ERROR: bleak not installed. Install with: pip install bleak")
    sys.exit(1)

try:
    from CasambiBt import Casambi
    from CasambiBt._constants import CASA_UUID
except ImportError:
    print("ERROR: CasambiBt not found. Make sure you've installed casambi-bt:")
    print("  cd /path/to/casambi-bt")
    print("  pip install -e .")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('casambi_esphome_monitor.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Suppress verbose logs
logging.getLogger("bleak").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("aioesphomeapi").setLevel(logging.INFO)


class ESPHomeProxyMonitor:
    def __init__(self, esphome_host, esphome_password, mac_address, network_password, cache_path):
        self.esphome_host = esphome_host
        self.esphome_password = esphome_password
        self.mac_address = mac_address
        self.network_password = network_password
        self.cache_path = cache_path

        self.api_client = None
        self.casa = None
        self.http_client = None

        self.connect_count = 0
        self.disconnect_count = 0
        self.reconnect_success = 0
        self.reconnect_failures = 0

        self.start_time = None
        self.last_disconnect_time = None

        self.esphome_can_see_device = False

    def _disconnect_callback(self):
        """Called when the device disconnects."""
        self.disconnect_count += 1
        self.last_disconnect_time = datetime.now()

        elapsed = (self.last_disconnect_time - self.start_time).total_seconds() if self.start_time else 0
        logger.warning(f"🔴 DISCONNECT #{self.disconnect_count} (after {elapsed:.1f}s)")

    async def connect_esphome_api(self):
        """Connect to the ESPHome API."""
        logger.info(f"Connecting to ESPHome API at {self.esphome_host}...")

        self.api_client = APIClient(
            address=self.esphome_host,
            port=6053,
            password=self.esphome_password,
        )

        try:
            await self.api_client.connect(login=True)
            logger.info("✓ ESPHome API connected")

            # Check if device supports Bluetooth proxy
            device_info = await self.api_client.device_info()
            logger.info(f"  Device: {device_info.name}")
            logger.info(f"  ESPHome version: {device_info.esphome_version}")

            # Check Bluetooth proxy support
            if hasattr(device_info, 'bluetooth_proxy_feature_flags'):
                flags = device_info.bluetooth_proxy_feature_flags
                logger.info(f"  Bluetooth proxy features: {flags}")

                # Check for pairing support
                if flags & BluetoothProxyFeature.PAIRING:
                    logger.info("  ✓ Pairing support: ENABLED")
                else:
                    logger.warning("  ⚠️  Pairing support: DISABLED")
                    logger.warning("     This may cause 'Insufficient authorization' errors!")
                    logger.warning("     Update ESPHome config with: cache_services: no")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect to ESPHome API: {e}")
            return False

    async def check_esphome_visibility(self):
        """Check if ESPHome proxy can see the Casambi device."""
        logger.info(f"Checking if ESPHome proxy can see device {self.mac_address}...")

        try:
            # Track if we've seen the device
            found = asyncio.Event()

            def on_bluetooth_le_advertisement(adv):
                """Handle Bluetooth advertisement."""
                # Convert address from bytes to MAC address string
                address = ":".join(f"{b:02X}" for b in adv.address)
                if address.upper() == self.mac_address.upper():
                    self.esphome_can_see_device = True
                    logger.info(f"✓ ESPHome proxy sees device: {adv.name} ({address}), RSSI: {adv.rssi}")
                    found.set()

            # Subscribe to advertisements (returns unsubscribe function, not a coroutine)
            unsub = self.api_client.subscribe_bluetooth_le_advertisements(
                on_bluetooth_le_advertisement
            )

            # Wait up to 15 seconds for device
            try:
                await asyncio.wait_for(found.wait(), timeout=15.0)
            except asyncio.TimeoutError:
                logger.warning(f"⚠️  Device {self.mac_address} not seen via ESPHome proxy after 15s")
                logger.warning("   This could mean:")
                logger.warning("   - Device is out of range of ESPHome proxy")
                logger.warning("   - Device is powered off")
                logger.warning("   - MAC address is incorrect")
            finally:
                # Unsubscribe from advertisements
                unsub()

            return self.esphome_can_see_device

        except Exception as e:
            logger.error(f"❌ Error checking ESPHome visibility: {e}")
            return False

    async def connect(self):
        """Connect to the Casambi network using direct BLE."""
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

            # Scan for device with Bleak
            logger.info("Scanning for Casambi device...")
            devices = await BleakScanner.discover(timeout=10.0, service_uuids=[CASA_UUID])

            device = None
            for d in devices:
                if d.address.upper() == self.mac_address.upper():
                    device = d
                    break

            # Handle macOS UUID vs MAC
            if not device and devices:
                # Check if we have a UUID format device and the user provided MAC
                if len(devices) == 1:
                    device = devices[0]
                    if len(device.address) == 36 and device.address.count('-') == 4:
                        logger.info(f"Note: macOS returned UUID {device.address}, using MAC {self.mac_address} for API")

            if not device:
                logger.error(f"❌ Device {self.mac_address} not found in local BLE scan")
                logger.error(f"   Found {len(devices)} Casambi device(s)")
                return False

            logger.info(f"Found device: {device.name} ({device.address})")

            # Determine if we need api_address parameter
            api_address = None
            if device.address.upper() != self.mac_address.upper():
                # macOS returns UUID, use MAC for API
                if len(device.address) == 36 and device.address.count('-') == 4:
                    logger.info(f"Using MAC {self.mac_address} for API lookups")
                    api_address = self.mac_address

            # Connect
            logger.info("Connecting to device...")
            await self.casa.connect(
                device,
                self.network_password,
                api_address=api_address
            )

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
            logger.debug(traceback.format_exc())
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
        logger.info("Starting connection monitor...")
        logger.info("=" * 60)

        # Connect initially
        if not await self.connect():
            logger.error("Initial connection failed. Exiting.")
            return

        start = time.time()
        next_check = start + check_interval

        try:
            while True:
                # Check if duration exceeded
                if duration_seconds and (time.time() - start) >= duration_seconds:
                    logger.info("Monitoring duration completed.")
                    break

                # Wait until next check time
                now = time.time()
                if now < next_check:
                    await asyncio.sleep(min(1, next_check - now))
                    continue

                next_check = now + check_interval

                # Check if still connected
                if self.casa.connected:
                    elapsed = now - start
                    logger.info(f"✓ Still connected ({elapsed:.0f}s elapsed)")

                    # Periodically re-check ESPHome visibility
                    if int(elapsed) % 120 == 0:  # Every 2 minutes
                        await self.check_esphome_visibility()
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

    def print_summary(self):
        """Print monitoring summary."""
        logger.info("=" * 60)
        logger.info("MONITORING SUMMARY")
        logger.info("=" * 60)
        print(f"ESPHome proxy can see device: {'YES' if self.esphome_can_see_device else 'NO/UNKNOWN'}")
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
    import argparse

    parser = argparse.ArgumentParser(
        description="Monitor Casambi BT connection and verify ESPHome Proxy visibility"
    )
    parser.add_argument("--esphome-host", type=str, required=True,
                       help="ESPHome device IP address or hostname")
    parser.add_argument("--esphome-password", type=str,
                       help="ESPHome API password (will prompt if not provided)")
    parser.add_argument("--mac-address", type=str, required=True,
                       help="Casambi device MAC address")
    parser.add_argument("--network-password", type=str,
                       help="Casambi network password (will prompt if not provided)")
    parser.add_argument("--duration", type=int,
                       help="Monitoring duration in seconds (omit for indefinite)")
    parser.add_argument("--interval", type=int, default=30,
                       help="Check interval in seconds (default: 30)")
    parser.add_argument("--cache", type=str, default="/tmp/casambi_cache",
                       help="Cache directory for Casambi data")

    args = parser.parse_args()

    # Get passwords if not provided
    esphome_password = args.esphome_password or getpass.getpass("Enter ESPHome API password: ")
    network_password = args.network_password or getpass.getpass("Enter Casambi network password: ")

    # Ensure cache directory exists
    cache_path = Path(args.cache)
    cache_path.mkdir(parents=True, exist_ok=True)

    # Create monitor
    monitor = ESPHomeProxyMonitor(
        esphome_host=args.esphome_host,
        esphome_password=esphome_password,
        mac_address=args.mac_address,
        network_password=network_password,
        cache_path=str(cache_path)
    )

    # Connect to ESPHome API
    logger.info("=" * 60)
    logger.info("ESPHome Proxy Monitor")
    logger.info("=" * 60)
    logger.info(f"ESPHome host: {args.esphome_host}")
    logger.info(f"Device MAC: {args.mac_address}")
    logger.info(f"Check interval: {args.interval}s")
    logger.info(f"Duration: {'Indefinite (Ctrl+C to stop)' if not args.duration else f'{args.duration}s'}")
    logger.info("=" * 60)

    if not await monitor.connect_esphome_api():
        logger.error("Failed to connect to ESPHome API. Exiting.")
        return 1

    # Check if ESPHome can see the device
    await monitor.check_esphome_visibility()

    if not monitor.esphome_can_see_device:
        logger.warning("")
        logger.warning("⚠️  ESPHome proxy cannot see the device!")
        logger.warning("    Continuing with direct BLE connection for comparison...")
        logger.warning("")

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
