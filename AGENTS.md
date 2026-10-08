# Notes for AI agents

This file records how the problem was diagnosed, so an agent facing the same or
a similar Bluetooth LE pairing failure can repeat the process instead of guessing.

## The finding in one paragraph

A Corsair Dark Core RGB Pro would not pair with an Intel AX201 adapter under
BlueZ. SMP pairing completed, but `LE Start Encryption` never produced an
`Encryption Change` event and BlueZ timed out after 30 s with
`AuthenticationCanceled`. Removing `LE2MTX LE2MRX LECODEDTX LECODEDRX` from the
adapter's selected PHYs with `btmgmt phy` fixed it. The kernel resets the PHY
selection on every adapter power-on, so a service re-applies it.

## How to apply the fix for a user

1. Check the symptom matches: `bluetoothctl pair <addr>` fails with
   `AuthenticationCanceled` after about 30 s, or connects and drops.
2. Read the current selection: `sudo btmgmt phy`. If "Selected phys" has no
   `LE2M*` entries, this fix does not apply; go to the diagnosis section.
3. Apply by hand first (it is temporary and harmless):
   take the adapter's "Selected phys" list, remove `LE2MTX LE2MRX LECODEDTX
   LECODEDRX`, and pass the rest to `sudo btmgmt phy <list>`.
4. Remove any stale device entry (`bluetoothctl remove <addr>`), ask the user to
   put the mouse in pairing mode, then pair and trust it.
5. Only if step 4 worked, run `sudo ./install.sh` to make it persistent.
6. Verify: `bluetoothctl power off; bluetoothctl power on`, then check that
   `btmgmt phy` still shows no `LE2M*` a few seconds later and that the mouse
   reconnects without help.

Pairing mode: mouse off, hold the profile button behind the scroll wheel, switch
to BT. It advertises as LE Limited Discoverable, with a static random address,
appearance Mouse (0x03c2) and service 0x1812.

## How the diagnosis went

The order matters; the early steps are cheap and rule out most of the search space.

1. **Check the adapter before blaming it.** Kernel log for `hci0` errors
   (timeouts, `-110`, `-71`, firmware load failures), a working classic device,
   an LE scan that sees other devices, and one real LE connection to any nearby
   LE device. All were clean, so the adapter and its antenna were fine.
2. **Web search.** Forums only had generic advice (pairing-mode button combo,
   one host at a time, firmware update). Nothing named a root cause.
3. **Capture a real attempt.** `btmon -w file.snoop` as root while a script
   (`tools/bt_pair_test.py`) scans, connects, pairs with an auto-accept agent and
   timestamps every D-Bus property change. Without the capture the only visible
   error is `AuthenticationCanceled`, which says nothing.
4. **Read the capture for what is missing.** Every command returned success. The
   signal was two absent events: no `Encryption Change` after `LE Start
   Encryption`, and no `LE Connection Update Complete` after `LE Connection
   Update`. Two link-layer procedures in a row that never finish, on a link that
   stays alive, point to the link-layer procedure queue being blocked.
5. **Change one variable per attempt.**
   - Connection interval 7.5 ms instead of 30–50 ms: same failure.
   - `Pair()` directly instead of `Connect()` then `Pair()`: same failure.
   - 1M PHY only: success in about one second.
6. **Verify persistence.** Power-cycling the adapter showed the kernel restores
   2M, which is why the fix needs a service and not a one-off command.

## Reading a capture: failing vs working

| Step | Failing (2M selected) | Working (1M only) |
| --- | --- | --- |
| LE connection | Success | Success |
| SMP request/response/confirm/random | Complete | Complete |
| `LE Start Encryption` command status | Success | Success |
| `Encryption Change` event | never arrives | arrives after 42 ms |
| Key distribution | none | LTK, IRK, identity address |
| Disconnect | by host after 30 s, Authentication Failure | none |

Excerpts: `docs/btmon-failing-2m-phy.txt`, `docs/btmon-working-1m-phy.txt`.

## Limits of this evidence

- HCI captures do not show link-layer PDUs. That a 2M PHY update is what stalls
  is an inference from the fix working, not something seen in the capture. Do not
  state it as observed fact.
- One mouse, one adapter (Intel AX201), one kernel (7.2.8), BlueZ 5.87.
- `ConnectionSupervisionTimeout=600` was set in `/etc/bluetooth/main.conf`
  during all tests.
- Windows was not tested.

## If the fix does not work elsewhere

Capture again and look for which expected event is missing. Other knobs that
exist and were not needed here: `btmgmt sc off` (legacy pairing only), connection
parameters under `[LE]` in `/etc/bluetooth/main.conf`, and
`/sys/kernel/debug/bluetooth/hci0/conn_{min,max}_interval` (write max before min
when raising, min before max when lowering, or the write fails with EINVAL).

## Practical notes

- `btmgmt phy` needs root; without it you get `Permission Denied (0x14)`.
- BlueZ's desktop agents (KDE, GNOME) compete for pairing prompts. Registering
  your own default agent that accepts `RequestAuthorization` avoids needing the
  user to click anything.
- Clean up after failed attempts with `Adapter1.RemoveDevice`, and leave the
  user's other paired devices alone.
