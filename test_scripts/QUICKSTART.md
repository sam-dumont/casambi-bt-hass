# Quick Start - Testing Network Level 11 Fix

## TL;DR - Fast Track

```bash
# 1. Clone your casambi-bt fork
git clone https://github.com/YOUR_USERNAME/casambi-bt.git ~/casambi-bt

# 2. Apply the fix
# Edit ~/casambi-bt/src/CasambiBt/_client.py
# Change line ~29: MAX_VERSION: Final[int] = 10
# To:             MAX_VERSION: Final[int] = 11

# 3. Run setup
cd ~/casambi-bt-hass/test_scripts
./setup.sh ~/casambi-bt

# 4. Test connection
./test_connection.py

# 5. If it fails, run debug
./debug_protocol.py
```

## Step-by-Step

### Step 1: Get Your Fork

You mentioned you forked casambi-bt. Clone it:

```bash
cd ~/
git clone https://github.com/YOUR_USERNAME/casambi-bt.git
```

### Step 2: Apply the Network Level 11 Fix

Open the file in your favorite editor:

```bash
nano ~/casambi-bt/src/CasambiBt/_client.py
# or
vim ~/casambi-bt/src/CasambiBt/_client.py
# or
code ~/casambi-bt/src/CasambiBt/_client.py
```

Find line ~29:
```python
MAX_VERSION: Final[int] = 10
```

Change to:
```python
MAX_VERSION: Final[int] = 11
```

Save and exit.

### Step 3: Install

```bash
cd ~/casambi-bt-hass/test_scripts
./setup.sh ~/casambi-bt
```

This will:
- Verify your fix is applied
- Install dependencies
- Install casambi-bt in development mode

### Step 4: Test!

```bash
./test_connection.py
```

Follow the prompts:
- Enter your Casambi device MAC address
- Enter your network password
- Optionally scan for devices first

### Step 5: Review Results

**If successful:**
- Check the output for "✓ CONNECTION SUCCESSFUL!"
- Note the protocol version (should be 11)
- Monitor for stability

**If failed:**
- Check `casambi_test.log` for details
- Run `./debug_protocol.py` for low-level analysis
- Share logs in GitHub issues #42 and #123

## What Next?

See **README.md** for:
- Detailed explanations
- Troubleshooting
- How to report results
- Next steps for contributing

## Quick Reference

### Your Hardware Info
Fill this in for reference:

- **Device MAC:** ___________________________
- **Network Name:** ___________________________
- **Firmware Version:** ___________________________
- **Device Model:** ___________________________

### Test Results

Date: _______________

- [ ] Connection successful
- [ ] Protocol version: ______
- [ ] Devices discovered: ______
- [ ] Stable for: ______ minutes/hours
- [ ] Logs attached: [ ] Yes [ ] No

### Issues Encountered

_______________________________________________
_______________________________________________
_______________________________________________
