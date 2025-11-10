# Casambi Network Level 11 Testing Guide

This directory contains test scripts to validate the network level 11 fix for Casambi BT integration.

## Overview

The scripts help you:
1. **test_connection.py** - Test basic connection with the patched library
2. **monitor_connection.py** - Monitor connection stability over time
3. **monitor_esphome_proxy.py** - Monitor connection via ESPHome Bluetooth proxy (Home Assistant setup)
4. **debug_protocol.py** - Capture detailed protocol packets for analysis

## Prerequisites

### 1. Clone Your Fork of casambi-bt

```bash
cd ~/
git clone https://github.com/YOUR_USERNAME/casambi-bt.git
cd casambi-bt
```

### 2. Apply the Network Level 11 Fix

Edit `src/CasambiBt/_client.py`:

Find (around line 28-29):
```python
MIN_VERSION: Final[int] = 10
MAX_VERSION: Final[int] = 10
```

Change to:
```python
MIN_VERSION: Final[int] = 10
MAX_VERSION: Final[int] = 11
```

Save the file.

### 3. Install the Modified Library

Install your modified version in development mode:

```bash
cd ~/casambi-bt
pip install -e .
```

This installs the library in "editable" mode, so changes you make are immediately available.

### 4. Install Dependencies

```bash
pip install bleak
```

## Running the Tests

### Test 1: Basic Connection Test

This test attempts a full connection using the Casambi library:

```bash
cd ~/casambi-bt-hass/test_scripts
python3 test_connection.py
```

**What it does:**
- Scans for your Casambi device
- Attempts to connect with your password
- Reports the protocol version
- Lists units, groups, and scenes if successful
- Saves detailed logs to `casambi_test.log`

**Expected Results:**

✅ **SUCCESS** - You should see:
```
✓ CONNECTION SUCCESSFUL!
  Network Name: Your Network
  Protocol Version: 11
```

❌ **FAILURE** - If it fails, you'll see error details and next steps.

### Test 2: Connection Stability Monitor

This script monitors your connection over time to track disconnections:

```bash
cd ~/casambi-bt-hass/test_scripts
./monitor_connection.py --address YOUR_MAC --password YOUR_PASSWORD --duration 3600
```

**What it does:**
- Maintains a connection for the specified duration
- Tracks connection/disconnection events
- Attempts automatic reconnection
- Reports statistics on stability
- Saves logs to `casambi_monitor.log`

**Options:**
- `--duration SECONDS` - How long to monitor (omit for indefinite)
- `--interval SECONDS` - Check interval (default: 10s)
- `--cache PATH` - Cache directory

### Test 3: ESPHome Bluetooth Proxy Monitor

This script tests connection via ESPHome Bluetooth proxy, mimicking Home Assistant's setup:

```bash
cd ~/casambi-bt-hass/test_scripts
./monitor_esphome_proxy.py \
  --esphome-host 192.168.1.100 \
  --mac-address YOUR_MAC \
  --duration 3600
```

**What it does:**
- Connects to your ESPHome device's Bluetooth proxy
- Verifies pairing support is enabled
- Scans for Casambi device via proxy
- Monitors connection stability through the proxy
- Reports disconnect/reconnect events
- Saves logs to `casambi_esphome_monitor.log`

**Required:**
- ESPHome device with Bluetooth proxy enabled
- ESPHome API password (will prompt if not provided)
- Casambi network password (will prompt if not provided)

**ESPHome Configuration Check:**

To ensure proper pairing support, your ESPHome config should have:
```yaml
bluetooth_proxy:
  active: true
  cache_services: no  # Important for pairing support
```

If `cache_services: yes`, you may see "Insufficient authorization (8)" errors on reconnection.

**Installation:**
```bash
pip install aioesphomeapi
```

Note: You don't need `bleak-esphome` - the script uses direct Bleak connections (same approach as HA).

### Test 4: Protocol Debug (Low-Level)

This script captures raw Bluetooth packets to analyze protocol changes:

```bash
cd ~/casambi-bt-hass/test_scripts
python3 debug_protocol.py
```

**What it does:**
- Connects at the Bluetooth LE level (bypasses Casambi library)
- Captures the initial key exchange packets
- Analyzes packet types and structure
- Saves detailed packet log to `casambi_packets.log`

**What to look for:**

If you see:
```
Type: 0x01 (KEY_EXCHANGE_INIT)
Protocol Version: 11
```
✅ This is GOOD - standard protocol with version 11

If you see:
```
Type: 0x07 (UNKNOWN_0x07)
✗ UNEXPECTED PACKET TYPE
```
⚠️ This indicates protocol changes beyond just version number

## Understanding the Results

### Scenario A: Connection Works! 🎉

If `test_connection.py` succeeds:
1. The basic version bump worked!
2. Monitor the connection for stability
3. Try controlling lights
4. Report success in issue #123

### Scenario B: Connection Fails with Protocol Error

If you get "Unexpected packet type 0x07":
1. This confirms network level 11 has protocol changes
2. The `casambi_packets.log` will show the exact packet structure
3. We'll need to reverse-engineer the new protocol
4. Share the packet log in issues #42 and #123

### Scenario C: Authentication Error

If you get "AUTHENTICATION ERROR":
- Double-check your network password
- Make sure the device address is correct
- Try clearing the cache: `rm -rf /tmp/casambi_cache`

## Collecting Debug Information

If the tests fail, collect these files to share:
- `casambi_test.log` - Full connection attempt log
- `casambi_packets.log` - Raw protocol packets
- Output from running the scripts

## Next Steps After Testing

### If Tests Pass ✅

1. **Use the integration normally** and monitor for disconnections
2. **Document your findings:**
   - Firmware version
   - How long the connection stays stable
   - Any errors that occur

3. **Update issue #123** with results:
   ```
   Tested with MAX_VERSION=11:
   - Firmware: Evolution/X.X
   - Connection: ✓ Success
   - Stability: [your observations]
   - Logs: [attach logs if any issues]
   ```

4. **Prepare PR for casambi-bt:**
   - Create PR with MAX_VERSION change
   - Reference issue #42 and #123
   - Include your test results

### If Tests Fail ❌

1. **Share debug information** in issue #42 and #123
2. **Include:**
   - Your firmware version
   - The error messages
   - The packet logs
   - Device model

3. **We may need to:**
   - Analyze the packet structure
   - Reverse-engineer protocol changes
   - Implement new key exchange logic

## Advanced: Home Assistant Testing

Once the basic connection works, you can test with Home Assistant:

### Option 1: Install Modified Library in HA

If using Home Assistant OS:
```bash
# SSH into HA
# Find the HA Python environment (usually /usr/local/lib/python*/site-packages)
# This is more complex - may need to modify the integration to use local library
```

### Option 2: Standalone Python Testing

Test the integration components standalone before running in HA:
```bash
cd ~/casambi-bt-hass
# Create test script that imports the integration components
# This lets you test without running full Home Assistant
```

## Troubleshooting

### "CasambiBt not found" Error

Make sure you installed with `pip install -e .` from the casambi-bt directory:
```bash
cd ~/casambi-bt
pip install -e .
```

### "Device not found" Error

1. Make sure Bluetooth is enabled
2. Device is powered on
3. Device address is correct (case-insensitive)
4. Try scanning first with the discovery option

### "Permission Denied" Bluetooth Error

On Linux, you may need:
```bash
sudo setcap 'cap_net_raw,cap_net_admin+eip' $(readlink -f $(which python3))
```

Or run with sudo (not recommended for production):
```bash
sudo python3 test_connection.py
```

## Questions?

- Open an issue in casambi-bt-hass repository
- Comment on issue #123
- Join the Discord (if link works): https://discord.gg/jgZVugfx

## Contributing

Once testing is complete and successful:

1. **Fork and create PR for casambi-bt** with MAX_VERSION change
2. **Update casambi-bt-hass** to require new casambi-bt version
3. **Document test results** in PR description
4. **Reference issues** #42 and #123

Thank you for testing! 🙏
