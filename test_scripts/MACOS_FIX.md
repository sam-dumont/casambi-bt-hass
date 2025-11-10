# macOS UUID vs MAC Address Fix

## Problem

On macOS, the Bluetooth LE stack (CoreBluetooth) assigns **random UUIDs** to unpaired BLE devices instead of exposing their actual MAC addresses. This causes the Casambi integration to fail:

1. **User enters**: MAC address `82:0A:EE:20:63:96`
2. **Scan finds**: UUID `5D15A905-7531-7FEB-E7C2-AA341D6D1516`
3. **Library tries**: API lookup with UUID → **404 Not Found**
4. **Result**: Connection fails

The Casambi cloud API only recognizes MAC addresses, not macOS UUIDs.

## Solution

We patched the **casambi-bt library** to add an `api_address` parameter:

```python
await casa.connect(
    device,              # BLEDevice with UUID address (for BLE connection)
    password,
    api_address="82:0A:EE:20:63:96"  # MAC address (for API lookups)
)
```

### What Changed

**casambi-bt library** (`~/casambi-bt/src/CasambiBt/_casambi.py`):
- Added `api_address` parameter to `connect()` method
- Uses `api_address` for cloud API lookups if provided
- Still uses `BLEDevice` (with UUID) for actual BLE connection
- Backwards compatible (parameter defaults to None)

**Test script** (`test_scripts/test_connection.py`):
- Detects when scanned address differs from entered address
- Checks if scanned address is UUID format (36 chars, 4 dashes)
- Automatically passes entered MAC as `api_address` parameter

### Additional Fix

Also fixed `setup.cfg` dependency:
- Changed: `aiopath==0.7.*` (doesn't exist)
- To: `aiopath>=0.6.11,<0.7`

## How to Use

### Option 1: Simple Test (no manual input)
```bash
cd test_scripts
./test_connection.py
```
- Answer 'n' to scanning
- Enter MAC: `82:0A:EE:20:63:96`
- Enter password

**The script automatically:**
1. Scans and finds UUID device
2. Detects UUID vs MAC mismatch
3. Passes MAC as `api_address` for API lookup
4. Uses UUID for BLE connection

### Option 2: With Device Discovery
```bash
cd test_scripts
./test_connection.py
```
- Answer 'y' to scanning
- Select device from list
- Script handles UUID/MAC automatically

## Testing

Try running the test now:

```bash
cd test_scripts
./test_connection.py
```

Expected flow:
```
Would you like to scan for Casambi devices first? (y/n): n
Enter your Casambi device MAC address: 82:0A:EE:20:63:96
Enter your network password (hidden): ********

Starting connection test...
Mode: ONLINE (cloud API lookup)

Looking for device 82:0A:EE:20:63:96...
No exact match for '82:0A:EE:20:63:96' in scan results
Found 1 Casambi device(s) total:
  - CV80W24CG IOT (5D15A905-7531-7FEB-E7C2-AA341D6D1516)
Using the discovered device: CV80W24CG IOT (5D15A905-7531-7FEB-E7C2-AA341D6D1516)
Detected UUID format - will use MAC '82:0A:EE:20:63:96' for API lookups
Attempting connection (with cloud API lookup)...
Using API address: 82:0A:EE:20:63:96, BLE address: 5D15A905-7531-7FEB-E7C2-AA341D6D1516
...
✓ CONNECTION SUCCESSFUL!
```

## Next Steps

1. **Test the connection** with your hardware
2. **Check protocol version** in the output (should be 11 if firmware is updated)
3. If successful, **push casambi-bt changes**:
   ```bash
   cd ~/casambi-bt
   git push origin main
   ```
4. **Update Home Assistant integration** to use the patched library

## Files Modified

### casambi-bt library
- `~/casambi-bt/src/CasambiBt/_casambi.py` - Added api_address parameter
- `~/casambi-bt/setup.cfg` - Fixed aiopath dependency
- Commit: `7b8687c`

### casambi-bt-hass
- `test_scripts/test_connection.py` - Auto-detect UUID and use api_address
- Branch: `claude/casambi-network-level-11-011CUv2zpaaBiYAfwtEA7vbr`
- Commit: `81af504`

## Technical Details

### Why This Works

1. **BLE Connection**: Uses `BLEDevice` object directly
   - CoreBluetooth only understands UUIDs
   - Must use UUID for actual connection

2. **API Lookup**: Uses MAC address string
   - Casambi cloud API only recognizes MACs
   - UUID results in 404 Not Found

3. **Cache Storage**: Uses API address (MAC) for cache key
   - Ensures cached data is accessible across UUID changes
   - macOS can assign different UUIDs across scans

### Backwards Compatibility

The change is fully backwards compatible:
- If `api_address` is not provided, uses `device.address` (old behavior)
- Works on Linux/Windows where `device.address` IS the MAC
- Only needed on macOS where `device.address` is a UUID

## Troubleshooting

If connection still fails, check:
1. **Cache directory**: Try with `--ha-cache --offline` to use existing cache
2. **Network password**: Ensure password is correct
3. **Device power**: Make sure device is on and in range
4. **Bluetooth**: Check macOS Bluetooth is enabled
5. **Logs**: Review `casambi_test.log` for detailed errors
