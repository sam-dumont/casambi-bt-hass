# ESPHome Bluetooth Proxy Testing

This guide explains how to test your Casambi connection through an ESPHome Bluetooth proxy device, replicating Home Assistant's connection behavior.

## Why This Matters

The "Insufficient authorization (8)" error you're seeing in Home Assistant logs occurs **during reconnection** when using ESPHome Bluetooth proxy, not during the initial connection. This script helps debug that specific scenario by:

1. Connecting through ESPHome proxy instead of direct BLE
2. Monitoring for disconnects and reconnection attempts
3. Checking if ESPHome has proper pairing support enabled
4. Logging detailed connection events

## Prerequisites

### 1. Install Dependencies

```bash
pip install aioesphomeapi bleak-esphome
```

### 2. Find Your ESPHome Device Info

You need:
- **IP address or hostname** of your ESPHome device (e.g., `192.168.1.100` or `esp-proxy.local`)
- **API password** for ESPHome (set in your ESPHome config)
- **MAC address** of your Casambi device (e.g., `82:0A:EE:20:63:96`)
- **Network password** for your Casambi network

### 3. Check ESPHome Configuration

Your ESPHome device should have Bluetooth proxy enabled with pairing support:

```yaml
bluetooth_proxy:
  active: true
  cache_services: no  # IMPORTANT: Must be 'no' for pairing support
```

**To check/edit your ESPHome config:**

1. Open ESPHome dashboard in Home Assistant (Settings → Add-ons → ESPHome → Open Web UI)
2. Click "EDIT" on your Bluetooth proxy device
3. Find the `bluetooth_proxy:` section
4. Ensure `cache_services: no` is set
5. If you change it, click "INSTALL" to update the device

## Running the Script

### Basic Usage

```bash
cd ~/casambi-bt-hass/test_scripts
./monitor_esphome_proxy.py \
  --esphome-host 192.168.1.100 \
  --mac-address 82:0A:EE:20:63:96
```

You'll be prompted for:
- ESPHome API password (hidden input)
- Casambi network password (hidden input)

### With All Options

```bash
./monitor_esphome_proxy.py \
  --esphome-host esp-proxy.local \
  --esphome-password "your-api-password" \
  --mac-address 82:0A:EE:20:63:96 \
  --network-password "your-network-password" \
  --duration 3600 \
  --interval 30 \
  --cache /tmp/casambi_cache
```

**Options:**
- `--esphome-host` - IP or hostname of ESPHome device (required)
- `--esphome-password` - ESPHome API password (will prompt if not provided)
- `--mac-address` - Casambi device MAC address (required)
- `--network-password` - Casambi network password (will prompt if not provided)
- `--duration SECONDS` - How long to monitor (omit for indefinite)
- `--interval SECONDS` - Check interval (default: 30s)
- `--cache PATH` - Cache directory (default: /tmp/casambi_cache)

## What to Look For

### ✅ Good Signs

```
✓ ESPHome API connected
  Device: esp-proxy
  ESPHome version: 2024.x.x
  ✓ Pairing support: ENABLED

Found device: CV80W24CG IOT (82:0A:EE:20:63:96), RSSI: -50

✅ CONNECTED (#1)
   Network: Mon Réseau
   Protocol: 11

✓ Still connected (60s elapsed)
✓ Still connected (120s elapsed)
```

### ⚠️ Warning Signs

```
⚠️  Pairing support: DISABLED
     This may cause 'Insufficient authorization' errors!
```

**Fix:** Update your ESPHome config with `cache_services: no`

### ❌ Problem: Reconnection Failure

```
🔴 DISCONNECT #1 (after 120.5s)
🔄 RECONNECT ATTEMPT...
❌ RECONNECT FAILED: BluetoothGATTErrorResponse: Insufficient authorization (8)
```

This is the exact error you're seeing in Home Assistant! The script captures:
- How long before first disconnect
- What error occurs during reconnect
- Full traceback for debugging

## Interpreting Results

### If Initial Connection Works But Reconnect Fails

This indicates a **pairing/bonding issue** with ESPHome proxy:

1. **Check ESPHome logs** during reconnect:
   ```bash
   # In Home Assistant
   Settings → Add-ons → ESPHome → Logs
   ```

2. **Verify pairing support** is enabled (script checks this automatically)

3. **Try clearing pairing data:**
   - Power cycle the ESPHome device
   - Clear Bluetooth bonds on ESPHome (if supported)
   - Restart the Casambi device

4. **Check ESPHome version:**
   - Pairing support added in ESPHome 2023.x
   - Update if using older version

### If Connection Works Indefinitely

Great! This means:
- ESPHome proxy configuration is correct
- Protocol v11 works properly
- The issue in Home Assistant might be elsewhere (integration logic, timing, etc.)

## Comparison with Direct BLE

Run both tests to compare behavior:

**Direct BLE (macOS/Linux):**
```bash
./monitor_connection.py --address 82:0A:EE:20:63:96
```

**Via ESPHome Proxy:**
```bash
./monitor_esphome_proxy.py --esphome-host 192.168.1.100 --mac-address 82:0A:EE:20:63:96
```

Compare:
- Time to first disconnect
- Reconnection success rate
- Error messages

## Troubleshooting

### "Failed to connect to ESPHome API"

1. Check ESPHome device is online: `ping 192.168.1.100`
2. Verify API password is correct
3. Check firewall allows port 6053
4. Ensure ESPHome API is enabled in config

### "Device not found via ESPHome proxy"

1. Check device is in range of ESPHome proxy
2. Verify MAC address is correct
3. Make sure device is powered on
4. Check ESPHome proxy is working (try scanning in HA)

### "Insufficient authorization" Immediately

This suggests:
1. Pairing is required but not supported
2. ESPHome has `cache_services: yes` (should be `no`)
3. Device requires bonding that ESPHome can't handle

## Logs

The script creates `casambi_esphome_monitor.log` with detailed information:
- ESPHome API connection events
- Bluetooth advertisements
- Connection attempts and results
- Disconnect/reconnect events
- Full error tracebacks

## Next Steps

After running this test:

1. **Share results** - Include the monitoring summary and relevant log excerpts
2. **Compare with direct BLE** - Does direct connection behave differently?
3. **Check ESPHome version** - Older versions may lack proper pairing support
4. **Investigate protocol v11 key exchange** - The "Unexpected answer from device" warning might be related

## Questions?

- Check the main [README.md](README.md) for more test scripts
- Review [MACOS_FIX.md](MACOS_FIX.md) for UUID/MAC address handling
- Open an issue with your test results

Good luck debugging! 🔍
