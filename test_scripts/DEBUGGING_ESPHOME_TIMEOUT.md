# Debugging ESPHome Proxy Connection Timeouts

Based on your Home Assistant logs, the Casambi connection is failing with:

```
TimeoutAPIError: Timeout waiting for connect response while connecting to 82:0A:EE:20:63:96 after 20.0s
```

This timeout happens **during BLE connection establishment**, before any Casambi protocol communication.

## What's Happening

From your logs:
1. HA finds 2 ESPHome proxies that can see your device:
   - `esp32-bluetooth-proxy-47be70` (RSSI=-83 to -97)
   - `esp32-bluetooth-proxy-44ed84` (RSSI=-97 to -104)

2. HA tries to connect through the proxy with best RSSI
3. Connection times out after 20 seconds
4. HA marks that proxy as "failed" and increments failure count
5. Next attempt tries the other proxy
6. Same timeout occurs
7. After 5 attempts, gives up with `BleakNotFoundError`

## Root Cause Analysis

The timeout during BLE connection (not authentication) suggests:

### 1. **ESPHome Proxy Can't Establish BLE Connection**

The ESPHome device can SEE the advertisements (RSSI shows it's receiving them) but CAN'T CONNECT.

**Possible causes:**
- Device rejects connection attempts from ESPHome
- ESPHome BLE stack issue
- Too many simultaneous connections
- Bluetooth chipset limitation

### 2. **Device-Side Connection Limits**

The Casambi device may:
- Only allow 1 active connection at a time
- Require pairing that ESPHome can't handle
- Have connection backoff after failed attempts

### 3. **ESPHome Proxy Configuration Issues**

Check your ESPHome proxy config:

```yaml
bluetooth_proxy:
  active: true
  cache_services: no  # CRITICAL for pairing
```

If `cache_services: yes`, the proxy won't properly handle pairing/bonding.

## Debugging Steps

### Step 1: Check ESPHome Proxy Configuration

**For each proxy (47be70 and 44ed84):**

1. Go to ESPHome dashboard in HA
2. Click "EDIT" on the proxy
3. Find `bluetooth_proxy:` section
4. Verify it has:
   ```yaml
   bluetooth_proxy:
     active: true
     cache_services: no
   ```
5. If you change it, click "INSTALL" to update

### Step 2: Check ESPHome Proxy Logs

**During a connection attempt:**

1. Settings → Add-ons → ESPHome → Logs (or logs for the specific device)
2. Watch for errors like:
   - "Bluetooth connection failed"
   - "Pairing failed"
   - "GATT error"
3. Look for the MAC address `82:0A:EE:20:63:96` in logs

### Step 3: Try Direct Connection (Bypass ESPHome)

**Temporarily connect HA host directly to Bluetooth:**

If your HA host has Bluetooth (not just via ESPHome), try connecting directly:

1. Disable ESPHome proxies temporarily
2. Enable Bluetooth on HA host
3. Try Casambi integration
4. If it works → ESPHome proxy is the problem
5. If it fails → Device-side issue

### Step 4: Reduce Signal Path Complexity

Move ONE ESPHome proxy very close to the Casambi device (RSSI > -50):

1. Better signal = less retry/timeout
2. Observe if connection succeeds
3. If yes → signal strength issue
4. If no → something else

### Step 5: Check for Connection Conflicts

**Ensure nothing else is connected:**

1. Turn off any other apps/devices that might be connected to Casambi
2. Power cycle the Casambi device
3. Wait 30 seconds
4. Try connecting again

### Step 6: ESPHome Proxy Reboot

Reboot BOTH ESPHome proxies:

1. Settings → Devices → (find each proxy)
2. Click reboot
3. Wait for them to come back online
4. Try connection again

## Advanced Debugging

### Check ESPHome Bluetooth Slots

From your logs:
```
(slots=3/3 free)
```

This shows 3 connection slots available. If this shows `(slots=0/3 free)`, the proxy is maxed out.

### Check Bluetooth Connection Failures

Your logs show:
```
(failures=0) → (failures=1) → (failures=2) → (failures=3) → (failures=4)
```

HA is tracking failures and penalizing unreliable proxies. After too many failures, it stops trying.

### Monitor RSSI Changes

```
RSSI=-83 → RSSI=-96 → RSSI=-104
```

Weakening signal during connection attempt suggests:
- Device is moving/mobile
- Interference
- Low battery

## Specific Tests

### Test 1: Verify ESPHome Can Connect to ANY BLE Device

Try connecting to a different BLE device through the same ESPHome proxy:
- If it works → Casambi device specific issue
- If it fails → ESPHome proxy BLE stack problem

### Test 2: Check ESPHome Version

Your proxy is running `2025.8.2`. Check if there are known Bluetooth issues:
1. Search ESPHome GitHub issues for "bluetooth timeout"
2. Check changelog for Bluetooth fixes in newer versions
3. Consider updating if fixes exist

### Test 3: Enable ESPHome Debug Logging

Add to your ESPHome config:
```yaml
logger:
  level: DEBUG
  logs:
    esp32_ble: DEBUG
    esp32_ble_tracker: DEBUG
```

This will show detailed BLE connection attempts.

## What We Know From Protocol v11 Testing

From your earlier successful tests:
- Protocol v11 connection WORKS with direct BLE (macOS)
- Initial connection sometimes succeeds in HA
- Reconnection fails

This suggests:
- Protocol v11 itself is not the root cause
- ESPHome proxy has issues with Casambi connection establishment
- Might be pairing/bonding related

## Possible Solutions

### Option 1: Use HA Host Bluetooth Directly

If your HA installation has Bluetooth hardware:
1. Enable Bluetooth integration in HA
2. Disable/remove ESPHome proxies from configuration
3. Connect directly

### Option 2: Different ESPHome Proxy Hardware

Some ESP32 boards have better Bluetooth performance:
- ESP32 (original) - good
- ESP32-C3 - better Bluetooth/WiFi coexistence
- ESP32-S3 - best Bluetooth performance

### Option 3: Update Casambi Library MAX_VERSION

You're seeing:
```
Version too new. Your network version is 11. Highest supported version is 10.
```

Update casambi-bt library to set `MAX_VERSION = 11`:
1. This might fix protocol-level issues
2. Could improve connection stability
3. Worth trying as next step

## Next Steps

1. **Check ESPHome config has `cache_services: no`** (most likely issue)
2. **Check ESPHome logs during connection attempt**
3. **Try rebooting both proxies**
4. **Move one proxy very close to device**
5. **Update casambi-bt to MAX_VERSION=11**
6. **Report findings in GitHub issues #42 and #123**

## Collect This Information

When reporting the issue, include:
- ESPHome version: `2025.8.2`
- ESP32 board model: (check in ESPHome)
- Casambi firmware version: `Evolution 46.0+`
- Protocol version: `11`
- ESPHome config (especially `bluetooth_proxy` section)
- Full ESPHome logs during connection attempt
- Distance between proxy and device (RSSI)

This will help diagnose the ESPHome proxy timeout issue.
