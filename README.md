# Corsair Dark Core RGB Pro — Bluetooth pairing fix (Linux)

The Corsair Dark Core RGB Pro would not pair over Bluetooth: it showed up in the
scan, connected for a moment, and then pairing failed. This repository documents
the root cause found with a packet capture and the fix that made it work.

**Short version:** the mouse says it supports the Bluetooth LE **2M PHY**, but the
link stalls when the adapter has 2M enabled. Limiting the adapter to the **1M PHY**
makes pairing finish in about one second, and the mouse reconnects on its own
afterwards.

Leer en español: [README.es.md](README.es.md) · For AI agents: [AGENTS.md](AGENTS.md)

## Symptoms

- The mouse appears in a Bluetooth scan as `DARK CORE RGB PRO`.
- `bluetoothctl pair` fails with `org.bluez.Error.AuthenticationCanceled` after about 30 seconds.
- `bluetoothctl connect` (without pairing) connects and drops a few seconds later.
- Desktop Bluetooth menus (KDE, GNOME) show "pairing failed" or connect/disconnect loops.
- The 2.4 GHz Slipstream dongle and the USB cable work fine.

## Quick fix

```sh
git clone https://github.com/Carlos12001/corsair-dark-core-rgb-pro-bluetooth-fix.git
cd corsair-dark-core-rgb-pro-bluetooth-fix
sudo ./install.sh
```

Then pair the mouse:

1. Switch the mouse off (switch on the bottom).
2. Hold the profile button (the one behind the scroll wheel).
3. While holding it, move the switch to **BT**. Release when the small LED between
   the wheel and the profile button blinks blue.
4. Pair it from your desktop's Bluetooth menu, or:

   ```sh
   bluetoothctl --timeout 15 scan le
   bluetoothctl devices | grep -i "dark core"     # note the address
   bluetoothctl pair  AA:BB:CC:DD:EE:FF
   bluetoothctl trust AA:BB:CC:DD:EE:FF
   ```

To undo everything: `sudo ./uninstall.sh`.

## Try it by hand first (nothing installed)

This is the whole fix. It lasts until Bluetooth is switched off and on again:

```sh
sudo btmgmt phy                 # look at "Selected phys": it lists LE2MTX LE2MRX
sudo btmgmt phy BR1M1SLOT BR1M3SLOT BR1M5SLOT EDR2M1SLOT EDR2M3SLOT EDR2M5SLOT \
                EDR3M1SLOT EDR3M3SLOT EDR3M5SLOT LE1MTX LE1MRX
sudo btmgmt phy                 # "Selected phys" must now end in: LE1MTX LE1MRX
```

The list keeps every classic Bluetooth (BR/EDR) packet type and drops only
`LE2MTX LE2MRX LECODEDTX LECODEDRX`. If your adapter's "Supported phys" line is
different, pass its own list minus those four.

Now put the mouse in pairing mode and pair it. If that works, install the service
so the setting survives.

## What the installer does

| File | Installed to | Purpose |
|---|---|---|
| `bt-le-1m-phy` | `/usr/local/bin/` | Applies the `btmgmt phy` command above, then watches BlueZ on D-Bus and re-applies it whenever the adapter is powered on |
| `bt-le-1m-phy.service` | `/etc/systemd/system/` | Runs the script with `bluetooth.target` |

The service is needed because the Linux kernel re-enables 2M and Coded PHY every
time the adapter is powered on (boot, Bluetooth toggle, airplane mode).

Requirements: BlueZ with `btmgmt`, `dbus-monitor`, systemd.

## Root cause

A `btmon` capture of the failing pairing shows this sequence
([full excerpt](docs/btmon-failing-2m-phy.txt)):

1. The LE connection is created successfully.
2. SMP pairing runs normally: Pairing Request, Pairing Response (legacy, Just Works),
   Confirm and Random values exchanged in both directions.
3. The host sends `LE Start Encryption` and the controller accepts the command.
4. **No `Encryption Change` event ever arrives.** The link stays up, but
   encryption never starts. A later `LE Connection Update` also never completes.
5. After 30 seconds BlueZ's SMP timer expires, it disconnects with
   "Authentication Failure", and the user sees `AuthenticationCanceled`.

With a plain connect and no pairing, the link went silent about 0.7 seconds after
connecting and died with "Connection Timeout".

With the adapter limited to the 1M PHY, the same sequence completes
([full excerpt](docs/btmon-working-1m-phy.txt)): `Encryption Change: Enabled with
AES-CCM` arrives 42 ms after `LE Start Encryption`, the keys are distributed, and
the HID service comes up.

The mouse reports these LE features: LE Encryption, Extended Reject Indication,
Data Packet Length Extension, **LE 2M PHY**, Channel Selection Algorithm #2.

### What is proven and what is inferred

- **Proven on this setup:** pairing fails every time with 2M PHY selected on the
  adapter (three captured attempts) and succeeded on the first attempt with 1M
  only. Reconnection after an adapter power cycle also works with 1M only.
- **Inferred:** that a 2M PHY update procedure stalls at the link layer and blocks
  the encryption procedure queued behind it. HCI captures do not show link-layer
  packets, so the capture cannot say whether the mouse or the adapter is the side
  that stalls. An over-the-air sniffer would be needed to settle that.
- **Ruled out:** connection interval (7.5 ms and 30–50 ms both failed with 2M) and
  the order of operations (connect-then-pair and pair-directly both failed with 2M).

## Tested setup

| | |
|---|---|
| Mouse | Corsair Dark Core RGB Pro, Bluetooth HID version 5.00 |
| Laptop | ASUS TUF Dash F15 FX517ZC |
| Bluetooth adapter | Intel AX201 (USB `8087:0026`), firmware `ibt-0040-4150` |
| OS | CachyOS (Arch-based), kernel 7.2.8 |
| BlueZ | 5.87 |
| Date | 2026-10-03 |

Things to know about this test:

- One mouse and one adapter. Other adapters may not need the fix, or may need it too.
- `ConnectionSupervisionTimeout=600` was already set under `[LE]` in
  `/etc/bluetooth/main.conf` from an earlier attempt. The fix was not re-tested
  without it.
- The successful first pairing happened with a 7.5 ms connection interval set
  through debugfs. Reconnection with the default 30–50 ms interval works; a fresh
  pairing with the default interval was not tested separately.
- A full reboot had not been tested when this was written, only an adapter power
  cycle.
- The same mouse also failed to pair on Windows on this laptop. The 2M PHY is a
  likely cause there too, but that has not been tested.

## Side effects

All Bluetooth LE devices on this adapter use the 1M PHY. Mice, keyboards and game
controllers are unaffected in practice. Devices that benefit from 2M (LE Audio
earbuds, fast file transfer over LE) get lower throughput. Classic Bluetooth
(most headphones, speakers) is not touched.

## Troubleshooting

```sh
systemctl status bt-le-1m-phy          # must be active
sudo btmgmt phy | grep ^Selected       # must not contain LE2M or LECODED
bluetoothctl info AA:BB:CC:DD:EE:FF    # Paired / Bonded / Trusted / Connected
```

- **The mouse does not show up in the scan.** It is not in pairing mode. It only
  advertises to new hosts when switched to BT with the profile button held.
- **It paired before the fix and now misbehaves.** Remove it and pair again:
  `bluetoothctl remove AA:BB:CC:DD:EE:FF`.
- **Still failing.** Capture it and compare with the excerpts in `docs/`:

  ```sh
  sudo btmon -w /tmp/mouse.snoop        # terminal 1, Ctrl+C when done
  python3 tools/bt_pair_test.py         # terminal 2, mouse in pairing mode
  btmon -r /tmp/mouse.snoop | less
  ```

  `tools/bt_pair_test.py` waits for the mouse, pairs it with an auto-accepting
  agent and logs every state change. Run it with `PAIR_FIRST=1` to skip the
  initial plain connect.

## Other things this mouse needs on Linux

- **RGB, DPI and buttons:** iCUE does not exist for Linux. `ckb-next` can
  configure the mouse over the dongle or cable (the daemon needs
  `--enable-experimental` for the Slipstream receiver `1b1c:1ba6`), but it cannot
  save profiles to the mouse's onboard memory and does not work over Bluetooth.

## License

MIT. See [LICENSE](LICENSE).
