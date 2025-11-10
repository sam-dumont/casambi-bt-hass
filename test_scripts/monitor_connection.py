#!/usr/bin/env python3
"""
Monitor Casambi BT connection stability over time.
This script connects, maintains the connection, and monitors for disconnections.
"""

import asyncio
import logging
import sys
import getpass
import time
from datetime import datetime
from pathlib import Path
from bleak import BleakScanner

try:
    from httpx import AsyncClient
except ImportError:
    print("ERROR: httpx not installed. Install with: pip install httpx")
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
        logging.FileHandler('casambi_monitor.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# Suppress bleak debug logs for cleaner output
logging.getLogger("bleak").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class ConnectionMonitor:
    def __init__(self, address, password, cache_path, api_address=None):
        self.address = address
        self.password = password
        self.cache_path = cache_path
        self.api_address = api_address

        self.casa = None
        self.http_client = None
        self.device = None

        self.connect_count = 0
        self.disconnect_count = 0
        self.reconnect_success = 0
        self.reconnect_failures = 0

        self.start_time = None
        self.last_disconnect_time = None
        self.disconnect_callback_received = False

    def _disconnect_callback(self):
        """Called when the device disconnects."""
        self.disconnect_count += 1
        self.last_disconnect_time = datetime.now()
        self.disconnect_callback_received = True

        elapsed = (self.last_disconnect_time - self.start_time).total_seconds() if self.start_time else 0
        logger.warning(f"🔴 DISCONNECT #{self.disconnect_count} (after {elapsed:.1f}s)")

    async def scan_device(self):
        """Scan for the Casambi device."""
        logger.info(f"Scanning for device {self.address}...")
        devices = await BleakScanner.discover(timeout=10, service_uuids=[CASA_UUID])

        # Try exact match first
        for d in devices:
            if d.address.upper() == self.address.upper():
                return d

        # Handle MAC vs UUID mismatch (macOS)
        if devices and len(devices) == 1:
            discovered = devices[0]
            logger.info(f"Using discovered device: {discovered.name} ({discovered.address})")

            # Detect if we need api_address (UUID vs MAC)
            if self.address.upper() != discovered.address.upper():
                # Check if discovered address is UUID format
                if len(discovered.address) == 36 and discovered.address.count('-') == 4:
                    logger.info(f"Detected UUID - will use MAC '{self.address}' for API lookups")
                    self.api_address = self.address

            return discovered

        return None

    async def connect(self):
        """Connect to the Casambi network."""
        try:
            logger.info(f"🔵 CONNECT ATTEMPT #{self.connect_count + 1}")

            # Scan for device if not already done
            if not self.device:
                self.device = await self.scan_device()
                if not self.device:
                    logger.error(f"Device {self.address} not found!")
                    return False

            # Create HTTP client if needed
            if not self.http_client:
                self.http_client = AsyncClient()

            # Create Casambi instance if needed
            if not self.casa:
                self.casa = Casambi(self.http_client, self.cache_path)

            # Register disconnect callback
            self.disconnect_callback_received = False
            self.casa.registerDisconnectCallback(self._disconnect_callback)

            # Connect
            await self.casa.connect(self.device, self.password, api_address=self.api_address)

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
                await asyncio.sleep(1)

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

    async def monitor(self, duration_seconds=None, check_interval=10):
        """Monitor the connection for a specified duration."""
        logger.info("=" * 60)
        logger.info("Starting connection monitoring...")
        logger.info(f"Check interval: {check_interval}s")
        if duration_seconds:
            logger.info(f"Duration: {duration_seconds}s ({duration_seconds/60:.1f} minutes)")
        else:
            logger.info("Duration: Indefinite (Ctrl+C to stop)")
        logger.info("=" * 60)

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

                    # Check if disconnect callback was triggered but connection still shows as active
                    if self.disconnect_callback_received:
                        logger.warning("⚠️  Disconnect callback triggered but connection shows active!")
                        self.disconnect_callback_received = False

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

    parser = argparse.ArgumentParser(description="Monitor Casambi BT connection stability")
    parser.add_argument("--address", type=str, required=True, help="Device MAC address")
    parser.add_argument("--password", type=str, help="Network password (will prompt if not provided)")
    parser.add_argument("--cache", type=str, default="/tmp/casambi_cache", help="Cache directory")
    parser.add_argument("--duration", type=int, help="Monitoring duration in seconds")
    parser.add_argument("--interval", type=int, default=10, help="Check interval in seconds (default: 10)")

    args = parser.parse_args()

    # Get password
    password = args.password
    if not password:
        password = getpass.getpass("Enter your network password: ")

    # Determine if we need api_address (macOS UUID handling)
    api_address = None
    if len(args.address) != 17 or args.address.count(':') != 5:
        # Might be a UUID, we'll detect during scan
        pass

    # Create monitor
    monitor = ConnectionMonitor(
        address=args.address,
        password=password,
        cache_path=Path(args.cache),
        api_address=api_address
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
