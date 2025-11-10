#!/usr/bin/env python3
"""
Basic connection test for Casambi BT with network level 11.
This script attempts to connect to your Casambi network and reports the status.
"""

import asyncio
import logging
import sys
import getpass
from pathlib import Path
from bleak import BleakScanner, BleakClient

# Add your casambi-bt path if installed with pip install -e
# sys.path.insert(0, '/path/to/casambi-bt/src')

try:
    from httpx import AsyncClient
except ImportError:
    print("ERROR: httpx not installed. Install with: pip install httpx")
    sys.exit(1)

try:
    from CasambiBt import Casambi, errors
    from CasambiBt._constants import CASA_UUID
    from CasambiBt.errors import (
        NetworkNotFoundError,
        NetworkOnlineUpdateNeededError,
        AuthenticationError,
        UnsupportedProtocolVersion,
        ProtocolError,
    )
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


async def test_connection(address, password, cache_path=Path('/tmp/casambi_cache'), use_offline=False):
    """Test connection to a Casambi network."""
    logger.info("="*60)
    logger.info(f"Testing connection to {address}")
    logger.info("="*60)

    casa = None
    http_client = None

    try:
        # Create HTTP client and Casambi instance
        logger.info("Creating Casambi instance...")
        logger.info(f"Using cache directory: {cache_path}")
        http_client = AsyncClient()
        casa = Casambi(http_client, cache_path)

        # Scan for the device
        logger.info(f"Looking for device {address}...")
        device = None
        devices = await BleakScanner.discover(timeout=10, service_uuids=[CASA_UUID])

        # Try exact match first
        for d in devices:
            if d.address.upper() == address.upper():
                device = d
                break

        # If no exact match and we found devices, handle MAC vs UUID mismatch
        if not device and devices:
            logger.info(f"No exact match for '{address}' in scan results")
            logger.info(f"Found {len(devices)} Casambi device(s) total:")
            for d in devices:
                logger.info(f"  - {d.name} ({d.address})")

            # On macOS, BLE scanner returns UUIDs, not MAC addresses
            # If user entered a MAC but we found exactly one Casambi device, use it
            if len(devices) == 1:
                logger.info("Note: On macOS, CoreBluetooth uses UUIDs instead of MAC addresses")
                logger.info(f"Using the discovered device: {devices[0].name} ({devices[0].address})")
                device = devices[0]
            else:
                logger.error(f"Multiple devices found. Please run the script with device discovery")
                logger.error("to select the correct device, or use one of the discovered UUIDs:")
                for d in devices:
                    logger.error(f"  - {d.address}")
                return False

        if not device:
            logger.error(f"Device {address} not found!")
            logger.error("Make sure:")
            logger.error("  1. The device is powered on and in range")
            logger.error("  2. Bluetooth is enabled on your system")
            logger.error("  3. Try scanning first (answer 'y' to discovery prompt)")
            return False

        logger.info(f"Found device: {device.name} ({device.address})")

        # Determine if we need to use api_address parameter
        api_address = None
        if address.upper() != device.address.upper():
            logger.info(f"Note: BLE device address '{device.address}' differs from requested '{address}'")
            # On macOS, device.address is a UUID, so use the original MAC for API lookups
            if len(device.address) == 36 and device.address.count('-') == 4:
                logger.info(f"Detected UUID format - will use MAC '{address}' for API lookups")
                api_address = address

        # Note: We DON'T clear cache here to avoid issues with UUID lookups
        # If you want to force a fresh connection, uncomment:
        # await casa.invalidateCache(device.address)

        # Attempt connection
        if use_offline:
            logger.info("Attempting connection in OFFLINE mode (using cached data)...")
            logger.info("Note: This requires cached network data from a previous connection")
            await casa.connect(device, password, forceOffline=True, api_address=api_address)
        else:
            logger.info("Attempting connection (with cloud API lookup)...")
            logger.info("Note: This will fetch network info from Casambi cloud API")
            if api_address:
                logger.info(f"Using API address: {api_address}, BLE address: {device.address}")
            await casa.connect(device, password, api_address=api_address)

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

    except errors.NetworkNotFoundError as e:
        logger.error(f"✗ NETWORK NOT FOUND: {e}")
        logger.error("")
        logger.error("This usually means the cloud API couldn't find your network.")
        logger.error("On macOS, CoreBluetooth uses random UUIDs that aren't recognized by Casambi API.")
        logger.error("")
        logger.error("SOLUTION: Use your Home Assistant cache directory which has the network data:")
        logger.error("  Run with: --ha-cache option or")
        logger.error("  Manually specify: --cache ~/.homeassistant/.storage/casambi_bt")
        return False
    except errors.NetworkOnlineUpdateNeededError as e:
        logger.error(f"✗ OFFLINE MODE ERROR: {e}")
        logger.error("")
        logger.error("Network data is not cached yet.")
        logger.error("Offline mode requires cached network data from a previous connection.")
        logger.error("")
        logger.error("SOLUTION: Don't use --offline flag on first connection,")
        logger.error("or use your Home Assistant cache directory which has the network data:")
        logger.error("  Run with: --ha-cache option")
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

        # Close HTTP client
        if http_client:
            try:
                await http_client.aclose()
            except Exception as e:
                logger.warning(f"Error closing HTTP client: {e}")


async def main():
    """Main test function."""
    import argparse

    parser = argparse.ArgumentParser(description="Test Casambi BT connection with network level 11 support")
    parser.add_argument("--cache", type=str, help="Cache directory path (default: /tmp/casambi_cache)")
    parser.add_argument("--ha-cache", action="store_true", help="Use Home Assistant cache directory")
    parser.add_argument("--offline", action="store_true", help="Use offline mode (requires cached data)")
    parser.add_argument("--address", type=str, help="Device MAC address or UUID")
    parser.add_argument("--no-scan", action="store_true", help="Skip device scanning")

    args = parser.parse_args()

    print("\n" + "="*60)
    print("Casambi BT Network Level 11 Connection Test")
    print("="*60 + "\n")

    # Determine cache directory
    if args.ha_cache:
        # Try to find Home Assistant config directory
        ha_config_paths = [
            Path.home() / ".homeassistant",
            Path("/config"),  # Docker/HAOS
        ]
        cache_path = None
        for ha_path in ha_config_paths:
            potential_cache = ha_path / ".storage" / "casambi_bt"
            if ha_path.exists():
                cache_path = potential_cache
                print(f"Using Home Assistant cache: {cache_path}")
                break
        if not cache_path:
            print("WARNING: Could not find Home Assistant config directory")
            print("Using default cache path instead")
            cache_path = Path("/tmp/casambi_cache")
    elif args.cache:
        cache_path = Path(args.cache)
        print(f"Using custom cache: {cache_path}")
    else:
        cache_path = Path("/tmp/casambi_cache")
        print(f"Using default cache: {cache_path}")

    print()

    # Configuration
    DEVICE_ADDRESS = args.address

    # Helper function to detect if address is a UUID (macOS CoreBluetooth format)
    def is_uuid(addr):
        # UUID format: 8-4-4-4-12 hex digits
        return len(addr) == 36 and addr.count('-') == 4

    # Optional: Auto-discover
    if not args.no_scan and not DEVICE_ADDRESS:
        discover = input("Would you like to scan for Casambi devices first? (y/n): ").strip().lower()
    else:
        discover = 'n'

    if discover == 'y':
        devices = await discover_casambi_devices()
        if devices:
            print()
            if len(devices) == 1:
                device_addr = devices[0].address
                device_name = devices[0].name

                # Check if it's a UUID (macOS)
                if is_uuid(device_addr):
                    print(f"Found device '{device_name}' with UUID (macOS CoreBluetooth): {device_addr}")
                    print("\nNote: On macOS, CoreBluetooth uses UUIDs instead of MAC addresses.")
                    use_uuid = input("Use this UUID for connection? (y=use UUID, n=enter MAC manually): ").strip().lower()
                    if use_uuid == 'y':
                        DEVICE_ADDRESS = device_addr
                    else:
                        DEVICE_ADDRESS = input("Enter the actual MAC address (e.g., AA:BB:CC:DD:EE:FF): ").strip()
                else:
                    use_device = input(f"Use found device '{device_name}' ({device_addr})? (y/n): ").strip().lower()
                    if use_device == 'y':
                        DEVICE_ADDRESS = device_addr
            else:
                print("\nSelect a device:")
                for i, device in enumerate(devices, 1):
                    addr_type = " (UUID)" if is_uuid(device.address) else ""
                    print(f"  {i}. {device.name} ({device.address}){addr_type}")
                selection = input("\nEnter device number (or press Enter to type address manually): ").strip()
                if selection.isdigit() and 1 <= int(selection) <= len(devices):
                    selected_device = devices[int(selection) - 1]
                    if is_uuid(selected_device.address):
                        print(f"\nSelected UUID: {selected_device.address}")
                        print("On macOS, you can use the UUID or enter the actual MAC address.")
                        use_uuid = input("Use UUID? (y=use UUID, n=enter MAC manually): ").strip().lower()
                        if use_uuid == 'y':
                            DEVICE_ADDRESS = selected_device.address
                        else:
                            DEVICE_ADDRESS = input("Enter the actual MAC address: ").strip()
                    else:
                        DEVICE_ADDRESS = selected_device.address

    if not DEVICE_ADDRESS:
        print()
        DEVICE_ADDRESS = input("Enter your Casambi device MAC address (e.g., AA:BB:CC:DD:EE:FF): ").strip()

    NETWORK_PASSWORD = getpass.getpass("Enter your network password (hidden): ")

    if not DEVICE_ADDRESS or not NETWORK_PASSWORD:
        print("ERROR: Both address and password are required!")
        return

    print("\nStarting connection test...")
    print(f"Logs are being saved to: casambi_test.log")
    if args.offline:
        print("Mode: OFFLINE (using cached data)")
    else:
        print("Mode: ONLINE (cloud API lookup)")
    print()

    # Run the test
    success = await test_connection(DEVICE_ADDRESS, NETWORK_PASSWORD, cache_path, args.offline)

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
