#!/usr/bin/env python3
"""
Basic connection test for Casambi BT with network level 11.
This script attempts to connect to your Casambi network and reports the status.
"""

import asyncio
import logging
import sys
import getpass
from bleak import BleakScanner, BleakClient

# Add your casambi-bt path if installed with pip install -e
# sys.path.insert(0, '/path/to/casambi-bt/src')

try:
    from CasambiBt import Casambi, errors
    from CasambiBt._constants import CASA_UUID
except ImportError:
    print("ERROR: CasambiBt not found. Make sure you've installed casambi-bt:")
    print("  cd /path/to/casambi-bt")
    print("  pip install -e .")
    sys.exit(1)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('casambi_test.log'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


async def discover_casambi_devices(timeout=10):
    """Scan for Casambi devices."""
    logger.info(f"Scanning for Casambi devices (timeout: {timeout}s)...")
    # When service_uuids is specified, BleakScanner already filters for us
    devices = await BleakScanner.discover(timeout=timeout, service_uuids=[CASA_UUID])

    logger.info(f"Found {len(devices)} Casambi device(s):")
    for device in devices:
        logger.info(f"  - {device.name} ({device.address})")

    return devices


async def test_connection(address, password, cache_dir='/tmp/casambi_cache'):
    """Test connection to a Casambi network."""
    logger.info("="*60)
    logger.info(f"Testing connection to {address}")
    logger.info("="*60)

    casa = None

    try:
        # Create Casambi instance
        logger.info("Creating Casambi instance...")
        casa = Casambi(cache_dir=cache_dir)

        # Scan for the device
        logger.info(f"Looking for device {address}...")
        device = None
        devices = await BleakScanner.discover(timeout=10, service_uuids=[CASA_UUID])

        for d in devices:
            if d.address.upper() == address.upper():
                device = d
                break

        if not device:
            logger.error(f"Device {address} not found!")
            return False

        logger.info(f"Found device: {device.name} ({device.address})")

        # Clear cache for fresh connection
        logger.info("Clearing cache for fresh connection test...")
        await casa.invalidateCache(address)

        # Attempt connection
        logger.info("Attempting connection...")
        await casa.connect(device, password)

        # Check connection status
        if casa.connected:
            logger.info("✓ CONNECTION SUCCESSFUL!")
            logger.info(f"  Network Name: {casa.networkName}")
            logger.info(f"  Network ID: {casa.networkId}")
            logger.info(f"  Protocol Version: {casa.protocolVersion}")

            # Get network info
            logger.info("\nNetwork Information:")
            logger.info(f"  Units: {len(casa.units)}")
            logger.info(f"  Groups: {len(casa.groups)}")
            logger.info(f"  Scenes: {len(casa.scenes)}")

            if casa.units:
                logger.info("\nUnits found:")
                for unit_id, unit in casa.units.items():
                    logger.info(f"  - {unit.name} (ID: {unit_id})")

            return True
        else:
            logger.error("✗ Connection failed - casa.connected is False")
            return False

    except errors.UnsupportedProtocolVersion as e:
        logger.error(f"✗ UNSUPPORTED PROTOCOL VERSION: {e}")
        return False
    except errors.AuthenticationError as e:
        logger.error(f"✗ AUTHENTICATION ERROR: {e}")
        logger.error("  Check your network password!")
        return False
    except errors.ProtocolError as e:
        logger.error(f"✗ PROTOCOL ERROR: {e}")
        logger.error("  This might indicate network level 11 protocol incompatibility")
        return False
    except Exception as e:
        logger.error(f"✗ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False
    finally:
        # Disconnect
        if casa and casa.connected:
            logger.info("Disconnecting...")
            try:
                await casa.disconnect()
                logger.info("Disconnected successfully")
            except Exception as e:
                logger.warning(f"Error during disconnect: {e}")


async def main():
    """Main test function."""
    print("\n" + "="*60)
    print("Casambi BT Network Level 11 Connection Test")
    print("="*60 + "\n")

    # Configuration
    # Optional: Auto-discover
    discover = input("Would you like to scan for Casambi devices first? (y/n): ").strip().lower()
    if discover == 'y':
        devices = await discover_casambi_devices()
        if devices:
            print("\nDevices found above. You can use one of these addresses.")

    print()
    DEVICE_ADDRESS = input("Enter your Casambi device MAC address (e.g., AA:BB:CC:DD:EE:FF): ").strip()
    NETWORK_PASSWORD = getpass.getpass("Enter your network password (hidden): ")

    if not DEVICE_ADDRESS or not NETWORK_PASSWORD:
        print("ERROR: Both address and password are required!")
        return

    print("\nStarting connection test...")
    print(f"Logs are being saved to: casambi_test.log\n")

    # Run the test
    success = await test_connection(DEVICE_ADDRESS, NETWORK_PASSWORD)

    print("\n" + "="*60)
    if success:
        print("TEST RESULT: ✓ SUCCESS - Connection works!")
        print("\nNext steps:")
        print("1. Check if the connection remains stable over time")
        print("2. Try controlling lights through the connection")
        print("3. Monitor for disconnections")
    else:
        print("TEST RESULT: ✗ FAILED - Connection did not work")
        print("\nNext steps:")
        print("1. Check the log file 'casambi_test.log' for details")
        print("2. Verify your network password is correct")
        print("3. Run the debug script for more detailed packet analysis")
    print("="*60 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)
