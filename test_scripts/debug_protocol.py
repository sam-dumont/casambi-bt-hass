#!/usr/bin/env python3
"""
Advanced protocol debugging script for Casambi BT network level 11.
This script captures detailed packet information during connection attempts.
"""

import asyncio
import logging
import sys
import struct
import getpass
from datetime import datetime
from pathlib import Path

try:
    from bleak import BleakScanner, BleakClient
    from bleak.backends.characteristic import BleakGATTCharacteristic
except ImportError:
    print("ERROR: bleak not installed. Install with: pip install bleak")
    sys.exit(1)

# Add your casambi-bt path if installed with pip install -e
# sys.path.insert(0, '/path/to/casambi-bt/src')

try:
    from CasambiBt._constants import CASA_UUID, CASA_AUTH_CHAR_UUID
except ImportError:
    print("ERROR: CasambiBt not found. Make sure you've installed casambi-bt:")
    print("  cd /path/to/casambi-bt")
    print("  pip install -e .")
    sys.exit(1)


# Packet capture storage
packet_log = []


def bytes_to_hex(data):
    """Convert bytes to hex string with spaces."""
    return ' '.join(f'{b:02x}' for b in data)


def analyze_packet(data, direction="RECV"):
    """Analyze and log packet details."""
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    hex_data = bytes_to_hex(data)

    packet_info = {
        'timestamp': timestamp,
        'direction': direction,
        'raw': data,
        'hex': hex_data,
        'length': len(data),
    }

    # Try to parse packet structure
    if len(data) >= 2:
        packet_type = data[0]
        packet_info['type'] = f"0x{packet_type:02x}"

        # Known packet types
        packet_types = {
            0x01: "KEY_EXCHANGE_INIT",
            0x02: "PUBLIC_KEY",
            0x03: "AUTH_REQUEST",
            0x07: "UNKNOWN_0x07 (SetColor in operations, but unexpected in auth)",
        }

        packet_info['type_name'] = packet_types.get(packet_type, f"UNKNOWN_0x{packet_type:02x}")

        # Parse based on packet type
        if packet_type == 0x01 and len(data) >= 22:
            # Key exchange init: type(1) | version(1) | mtu(1) | unit(2) | flags(2) | nonce(16)
            try:
                version = data[1]
                mtu = data[2]
                unit, flags = struct.unpack_from(">HH", data, 3)
                nonce = data[7:23] if len(data) >= 23 else data[7:]

                packet_info['parsed'] = {
                    'protocol_version': version,
                    'mtu': mtu,
                    'unit': unit,
                    'flags': f"0x{flags:04x}",
                    'nonce': bytes_to_hex(nonce),
                }
            except Exception as e:
                packet_info['parse_error'] = str(e)

        elif packet_type == 0x02 and len(data) >= 65:
            # Public key: type(1) | x(32) | y(32)
            packet_info['parsed'] = {
                'public_key_x': bytes_to_hex(data[1:33]),
                'public_key_y': bytes_to_hex(data[33:65]),
            }

        elif packet_type == 0x07:
            # Unknown packet type for authentication phase
            packet_info['parsed'] = {
                'note': 'This packet type (0x07) is unexpected during authentication!',
                'possible_cause': 'Network level 11 protocol change',
                'next_bytes': bytes_to_hex(data[1:min(20, len(data))]),
            }

    packet_log.append(packet_info)
    return packet_info


def log_packet(packet_info):
    """Log packet information in a readable format."""
    print(f"\n[{packet_info['timestamp']}] {packet_info['direction']} - Length: {packet_info['length']} bytes")
    print(f"  Type: {packet_info.get('type', 'N/A')} ({packet_info.get('type_name', 'Unknown')})")
    print(f"  Raw: {packet_info['hex']}")

    if 'parsed' in packet_info:
        print(f"  Parsed:")
        for key, value in packet_info['parsed'].items():
            print(f"    {key}: {value}")

    if 'parse_error' in packet_info:
        print(f"  Parse Error: {packet_info['parse_error']}")


async def debug_connection(address, password):
    """Debug connection with detailed packet logging."""
    print("="*80)
    print(f"PROTOCOL DEBUG - Connecting to {address}")
    print("="*80)

    client = None

    def notification_handler(characteristic: BleakGATTCharacteristic, data: bytearray):
        """Handle notifications from device."""
        packet_info = analyze_packet(data, "RECV_NOTIFY")
        log_packet(packet_info)

    try:
        # Scan for device
        print(f"\n[1/5] Scanning for device {address}...")
        devices = await BleakScanner.discover(timeout=10, service_uuids=[CASA_UUID])

        device = None
        for d in devices:
            if d.address.upper() == address.upper():
                device = d
                break

        if not device:
            print(f"ERROR: Device {address} not found!")
            return False

        print(f"  ✓ Found: {device.name} ({device.address})")

        # Connect to device
        print(f"\n[2/5] Connecting to device...")
        client = BleakClient(device)
        await client.connect()
        print(f"  ✓ Connected via Bluetooth LE")

        # Read initial packet
        print(f"\n[3/5] Reading initial key exchange packet...")
        print(f"  Reading characteristic: {CASA_AUTH_CHAR_UUID}")

        initial_response = await client.read_gatt_char(CASA_AUTH_CHAR_UUID)
        packet_info = analyze_packet(initial_response, "RECV_READ")
        log_packet(packet_info)

        # Check protocol version
        if len(initial_response) >= 2:
            if initial_response[0] == 0x01:
                protocol_version = initial_response[1]
                print(f"\n  ✓ Standard key exchange init received")
                print(f"  Protocol Version: {protocol_version}")

                if protocol_version == 11:
                    print(f"  ⚠ Network Level 11 detected!")
                elif protocol_version == 10:
                    print(f"  ✓ Network Level 10 (baseline)")
            else:
                print(f"\n  ✗ UNEXPECTED PACKET TYPE: 0x{initial_response[0]:02x}")
                print(f"  Expected: 0x01 (KEY_EXCHANGE_INIT)")
                print(f"  This indicates a protocol change in network level 11!")

                if initial_response[0] == 0x07:
                    print(f"\n  Analysis:")
                    print(f"    - Packet type 0x07 is used for SetColor in device control")
                    print(f"    - It should NOT appear during authentication")
                    print(f"    - Network level 11 may have changed the auth handshake")
                    print(f"    - Further reverse engineering needed")

                return False

        # Start notifications
        print(f"\n[4/5] Starting notifications...")
        await client.start_notify(CASA_AUTH_CHAR_UUID, notification_handler)
        print(f"  ✓ Notifications enabled")

        # Wait for device-initiated messages
        print(f"\n[5/5] Waiting for device messages (10 seconds)...")
        print(f"  (The device should send its public key...)")

        await asyncio.sleep(10)

        print(f"\n  Capture complete")

        return True

    except Exception as e:
        print(f"\n✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if client and client.is_connected:
            print(f"\nDisconnecting...")
            try:
                await client.stop_notify(CASA_AUTH_CHAR_UUID)
            except:
                pass
            await client.disconnect()
            print(f"  ✓ Disconnected")


def save_packet_log(filename="casambi_packets.log"):
    """Save packet log to file."""
    with open(filename, 'w') as f:
        f.write("="*80 + "\n")
        f.write("CASAMBI PROTOCOL DEBUG LOG\n")
        f.write(f"Timestamp: {datetime.now()}\n")
        f.write("="*80 + "\n\n")

        for packet in packet_log:
            f.write(f"[{packet['timestamp']}] {packet['direction']}\n")
            f.write(f"  Length: {packet['length']} bytes\n")
            f.write(f"  Type: {packet.get('type', 'N/A')} ({packet.get('type_name', 'Unknown')})\n")
            f.write(f"  Hex: {packet['hex']}\n")

            if 'parsed' in packet:
                f.write(f"  Parsed:\n")
                for key, value in packet['parsed'].items():
                    f.write(f"    {key}: {value}\n")

            if 'parse_error' in packet:
                f.write(f"  Parse Error: {packet['parse_error']}\n")

            f.write("\n")

    print(f"\nPacket log saved to: {filename}")


async def main():
    """Main debug function."""
    print("\n" + "="*80)
    print("CASAMBI BT PROTOCOL DEBUGGER - Network Level 11 Analysis")
    print("="*80 + "\n")

    print("This script will capture and analyze the Bluetooth packets exchanged")
    print("during connection to help identify network level 11 protocol changes.\n")

    # Configuration
    DEVICE_ADDRESS = input("Enter your Casambi device MAC address: ").strip()
    NETWORK_PASSWORD = getpass.getpass("Enter your network password (hidden): ")

    if not DEVICE_ADDRESS or not NETWORK_PASSWORD:
        print("ERROR: Both address and password are required!")
        return

    print("\nNOTE: This debug script only performs LOW-LEVEL Bluetooth communication.")
    print("      It does NOT use the full Casambi library authentication.")
    print("      This allows us to see exactly what the device sends.\n")

    input("Press ENTER to start debugging...")

    # Run debug
    await debug_connection(DEVICE_ADDRESS, NETWORK_PASSWORD)

    # Save log
    if packet_log:
        print("\n" + "="*80)
        print(f"Captured {len(packet_log)} packet(s)")
        save_packet_log()

        print("\nSummary:")
        print(f"  Total packets: {len(packet_log)}")
        print(f"  Received: {sum(1 for p in packet_log if p['direction'].startswith('RECV'))}")
        print(f"  Sent: {sum(1 for p in packet_log if p['direction'] == 'SEND')}")

        # Check for 0x07 packets
        type_07_packets = [p for p in packet_log if p.get('type') == '0x07']
        if type_07_packets:
            print(f"\n  ⚠ WARNING: Found {len(type_07_packets)} packet(s) with type 0x07")
            print(f"    This confirms the network level 11 protocol change!")

        print("\nPlease share this information in GitHub issue #42 and #123")
    else:
        print("\nNo packets captured - connection may have failed before packet exchange")

    print("="*80 + "\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nDebug interrupted by user")
        if packet_log:
            save_packet_log()
        sys.exit(0)
