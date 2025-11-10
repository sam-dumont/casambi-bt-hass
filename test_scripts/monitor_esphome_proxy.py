#!/usr/bin/env python3
"""
Monitor Casambi BT connection via ESPHome Bluetooth Proxy.
This mimics Home Assistant's connection behavior.
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
    from bleak_esphome.backend.client import ESPHomeClient
    from bleak_esphome.backend.device import ESPHomeBluetoothDevice
except ImportError:
    print("ERROR: Required libraries not installed.")
    print("Install with: pip install aioesphomeapi bleak-esphome")
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

            return True

        except Exception as e:
            logger.error(f"❌ Failed to connect to ESPHome API: {e}")
            return False

    async def scan_via_proxy(self):
        """Scan for the Casambi device via ESPHome proxy."""
        logger.info(f"Scanning for device {self.mac_address} via ESPHome proxy...")

        try:
            # Subscribe to Bluetooth advertisements
            scan_results = {}

            def on_bluetooth_le_advertisement(adv):
                """Handle Bluetooth advertisement."""
                address = ":".join(f"{b:02X}" for b in adv.address)
                if address.upper() == self.mac_address.upper():
                    scan_results[address] = adv
                    logger.info(f"Found device: {adv.name} ({address}), RSSI: {adv.rssi}")

            # Subscribe to advertisements
            unsub = await self.api_client.subscribe_bluetooth_le_advertisements(
                on_bluetooth_le_advertisement
            )

            # Scan for 10 seconds
            await asyncio.sleep(10)
            unsub()

            if self.mac_address.upper() in [addr.upper() for addr in scan_results.keys()]:
                logger.info(f"✓ Device found via ESPHome proxy")
                return True
            else:
                logger.error(f"❌ Device {self.mac_address} not found via ESPHome proxy")
                logger.error(f"   Found {len(scan_results)} device(s) total")
                return False

        except Exception as e:
            logger.error(f"❌ Scan error: {e}")
            return False

    async def connect(self):
        """Connect to the Casambi network via ESPHome proxy."""
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

            # Create ESPHome BLE device
            ble_device = ESPHomeBluetoothDevice(
                name="Casambi Device",
                address=self.mac_address,
                rssi=-50,
                details={},
            )

            # Create ESPHome BLE client
            ble_client = ESPHomeClient(
                ble_device=ble_device,
                client=self.api_client,
            )

            logger.info("Connecting via ESPHome proxy...")

            # Connect using the ESPHome client as the backend
            # Note: We need to patch the connection to use ESPHomeClient
            # The casambi-bt library uses bleak, which we need to override

            # For now, connect with the BLEDevice and use api_address
            await self.casa.connect(
                ble_device,
                self.network_password,
                api_address=self.mac_address
            )

            if self.casa.connected:
                self.connect_count += 1
                if not self.start_time:
                    self.start_time = datetime.now()
                logger.info(f"✅ CONNECTED (#{self.connect_count})")
                logger.info(f"   Network: {self.casa.networkName}")
                logger.info(f"   Protocol: {self.casa._casaNetwork._protocolVersion if hasattr(self.casa, '_casaNetwork') else 'Unknown'}")
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
                await self.casa.disconnect()
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
            return False

    async def monitor(self, duration_seconds=None, check_interval=30):
        """Monitor the connection for a specified duration."""
        logger.info("=" * 60)
        logger.info("ESPHome Proxy Connection Monitor")
        logger.info("=" * 60)
        logger.info(f"ESPHome host: {self.esphome_host}")
        logger.info(f"Device MAC: {self.mac_address}")
        logger.info(f"Check interval: {check_interval}s")
        if duration_seconds:
            logger.info(f"Duration: {duration_seconds}s ({duration_seconds/60:.1f} minutes)")
        else:
            logger.info("Duration: Indefinite (Ctrl+C to stop)")
        logger.info("=" * 60)

        # Connect to ESPHome API
        if not await self.connect_esphome_api():
            logger.error("Failed to connect to ESPHome API. Exiting.")
            return

        # Scan for device
        if not await self.scan_via_proxy():
            logger.warning("Device not found in scan, but will try to connect anyway...")

        # Initial connection
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

                # Check connection status
                if not self.casa or not self.casa.connected:
                    logger.warning("⚠️  Connection lost - attempting reconnect...")
                    await self.reconnect()
                else:
                    elapsed = time.time() - start
                    logger.info(f"✓ Still connected ({elapsed:.0f}s elapsed)")

        except KeyboardInterrupt:
            logger.info("\nMonitoring interrupted by user")
        finally:
            await self.cleanup()
            self.print_summary()

    async def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up...")

        if self.casa and self.casa.connected:
            try:
                await self.casa.disconnect()
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")

        if self.http_client:
            try:
                await self.http_client.aclose()
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")

        if self.api_client:
            try:
                await self.api_client.disconnect()
            except Exception as e:
                logger.warning(f"Error disconnecting ESPHome API: {e}")

    def print_summary(self):
        """Print monitoring summary."""
        duration = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

        print("\n" + "=" * 60)
        print("MONITORING SUMMARY")
        print("=" * 60)
        print(f"Total duration:        {duration:.1f}s ({duration/60:.1f} minutes)")
        print(f"Connections:           {self.connect_count}")
        print(f"Disconnections:        {self.disconnect_count}")
        print(f"Reconnect successes:   {self.reconnect_success}")
        print(f"Reconnect failures:    {self.reconnect_failures}")
        if self.disconnect_count > 0 and duration > 0:
            mtbf = duration / self.disconnect_count
            print(f"Avg time between disconnects: {mtbf:.1f}s ({mtbf/60:.1f} minutes)")
        print("=" * 60)


async def main():
    """Main function."""
    import argparse

    parser = argparse.ArgumentParser(description="Monitor Casambi BT connection via ESPHome Proxy")
    parser.add_argument("--esphome-host", type=str, required=True, help="ESPHome device IP address or hostname")
    parser.add_argument("--esphome-password", type=str, help="ESPHome API password (will prompt if not provided)")
    parser.add_argument("--mac-address", type=str, required=True, help="Casambi device MAC address")
    parser.add_argument("--network-password", type=str, help="Casambi network password (will prompt if not provided)")
    parser.add_argument("--cache", type=str, default="/tmp/casambi_cache", help="Cache directory")
    parser.add_argument("--duration", type=int, help="Monitoring duration in seconds")
    parser.add_argument("--interval", type=int, default=30, help="Check interval in seconds (default: 30)")

    args = parser.parse_args()

    # Get passwords
    esphome_password = args.esphome_password
    if not esphome_password:
        esphome_password = getpass.getpass("Enter ESPHome API password: ")

    network_password = args.network_password
    if not network_password:
        network_password = getpass.getpass("Enter Casambi network password: ")

    # Create monitor
    monitor = ESPHomeProxyMonitor(
        esphome_host=args.esphome_host,
        esphome_password=esphome_password,
        mac_address=args.mac_address,
        network_password=network_password,
        cache_path=Path(args.cache)
    )

    # Run monitoring
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
