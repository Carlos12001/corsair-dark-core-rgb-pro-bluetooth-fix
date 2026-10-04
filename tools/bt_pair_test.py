#!/usr/bin/env python3
"""Wait for the Dark Core RGB Pro to advertise over BLE, connect, auto-accept
pairing, and log every state change with timestamps."""
import os, sys, time
import dbus, dbus.service, dbus.mainloop.glib
from gi.repository import GLib

NAME_MATCH = "DARK CORE"
WAIT_ADV = 90      # seconds to wait for the mouse to show up
PAIR_WAIT = 20      # seconds to wait for mouse-initiated pairing before host Pair()
STABLE_WATCH = 60   # seconds to watch the link after pairing
AGENT_PATH = "/claude/agent"

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()
loop = GLib.MainLoop()
T0 = time.time()
state = {"path": None, "phase": "scan", "paired": False, "result": "timeout: mouse never advertised"}


def log(msg):
    print(f"[{time.time() - T0:7.2f}] {msg}", flush=True)


class Agent(dbus.service.Object):
    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Release(self): log("agent: Release")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="")
    def RequestAuthorization(self, dev): log(f"agent: RequestAuthorization {dev} -> yes")

    @dbus.service.method("org.bluez.Agent1", in_signature="ou", out_signature="")
    def RequestConfirmation(self, dev, key): log(f"agent: RequestConfirmation {dev} {key} -> yes")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def AuthorizeService(self, dev, uuid): log(f"agent: AuthorizeService {dev} {uuid} -> yes")

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="s")
    def RequestPinCode(self, dev): log("agent: RequestPinCode -> 0000"); return "0000"

    @dbus.service.method("org.bluez.Agent1", in_signature="o", out_signature="u")
    def RequestPasskey(self, dev): log("agent: RequestPasskey -> 0"); return dbus.UInt32(0)

    @dbus.service.method("org.bluez.Agent1", in_signature="ouq", out_signature="")
    def DisplayPasskey(self, dev, key, entered): log(f"agent: DisplayPasskey {key}")

    @dbus.service.method("org.bluez.Agent1", in_signature="os", out_signature="")
    def DisplayPinCode(self, dev, pin): log(f"agent: DisplayPinCode {pin}")

    @dbus.service.method("org.bluez.Agent1", in_signature="", out_signature="")
    def Cancel(self): log("agent: Cancel")


def dev_iface():
    return dbus.Interface(bus.get_object("org.bluez", state["path"]), "org.bluez.Device1")


def dev_props():
    p = dbus.Interface(bus.get_object("org.bluez", state["path"]), "org.freedesktop.DBus.Properties")
    return p.GetAll("org.bluez.Device1")


def finish(result):
    state["result"] = result
    log(f"RESULT: {result}")
    loop.quit()


def found(path, props):
    if state["path"]:
        return
    name = str(props.get("Name", props.get("Alias", "")))
    if NAME_MATCH not in name.upper():
        return
    state["path"] = path
    log(f"found {name} at {props.get('Address')} type={props.get('AddressType')} rssi={props.get('RSSI')}")
    for k in ("Appearance", "UUIDs", "ManufacturerData", "AdvertisingFlags", "Paired", "Bonded"):
        if k in props:
            log(f"  adv {k} = {props[k]}")
    try:
        adapter.StopDiscovery()
    except dbus.DBusException as e:
        log(f"StopDiscovery: {e.get_dbus_name()}")
    GLib.timeout_add(500, maybe_pair if os.environ.get('PAIR_FIRST') else do_connect)


def do_connect():
    state["phase"] = "connect"
    log("calling Connect()")
    dev_iface().Connect(reply_handler=lambda: log("Connect() returned OK"),
                        error_handler=lambda e: log(f"Connect() error: {e.get_dbus_name()} {e.get_dbus_message()}"),
                        timeout=45)
    GLib.timeout_add_seconds(PAIR_WAIT, maybe_pair)
    return False


def maybe_pair():
    if state["paired"]:
        return False
    log("calling Pair()")
    state["phase"] = "pair"
    dev_iface().Pair(reply_handler=lambda: log("Pair() returned OK"),
                     error_handler=pair_failed, timeout=60)
    return False


def pair_failed(e):
    log(f"Pair() error: {e.get_dbus_name()} {e.get_dbus_message()}")
    if not state["paired"]:
        finish(f"pairing failed: {e.get_dbus_name()}")


def after_paired():
    state["phase"] = "watch"
    try:
        dbus.Interface(bus.get_object("org.bluez", state["path"]),
                       "org.freedesktop.DBus.Properties").Set("org.bluez.Device1", "Trusted", True)
        log("set Trusted=true")
    except dbus.DBusException as e:
        log(f"Trusted: {e}")
    GLib.timeout_add_seconds(STABLE_WATCH, end_watch)
    return False


def end_watch():
    p = dev_props()
    finish(f"after {STABLE_WATCH}s watch: Paired={bool(p['Paired'])} Bonded={bool(p.get('Bonded', False))} "
           f"Connected={bool(p['Connected'])} ServicesResolved={bool(p['ServicesResolved'])}")
    return False


def on_props(iface, changed, invalidated, path=None):
    if iface != "org.bluez.Device1":
        return
    if state["path"] is None:
        om = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
        objs = om.GetManagedObjects()
        if path in objs and "org.bluez.Device1" in objs[path]:
            found(path, objs[path]["org.bluez.Device1"])
        return
    if path != state["path"]:
        return
    for k, v in changed.items():
        if k in ("RSSI", "ManufacturerData", "TxPower"):
            continue
        log(f"prop {k} = {v if k != 'UUIDs' else [str(u)[:8] for u in v]}")
    if changed.get("Paired") and not state["paired"]:
        state["paired"] = True
        GLib.timeout_add(200, after_paired)


def on_added(path, ifaces):
    if "org.bluez.Device1" in ifaces:
        found(path, ifaces["org.bluez.Device1"])


def on_removed(path, ifaces):
    if path == state["path"] and "org.bluez.Device1" in ifaces:
        log("device object removed by BlueZ")


def no_adv():
    if state["path"] is None:
        finish(state["result"])
    return False


agent = Agent(bus, AGENT_PATH)
mgr = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
mgr.RegisterAgent(AGENT_PATH, "KeyboardDisplay")
mgr.RequestDefaultAgent(AGENT_PATH)
log("agent registered as default")

bus.add_signal_receiver(on_props, dbus_interface="org.freedesktop.DBus.Properties",
                        signal_name="PropertiesChanged", path_keyword="path")
bus.add_signal_receiver(on_added, dbus_interface="org.freedesktop.DBus.ObjectManager", signal_name="InterfacesAdded")
bus.add_signal_receiver(on_removed, dbus_interface="org.freedesktop.DBus.ObjectManager", signal_name="InterfacesRemoved")

adapter = dbus.Interface(bus.get_object("org.bluez", "/org/bluez/hci0"), "org.bluez.Adapter1")
# drop any stale object for the mouse so we start clean
om = dbus.Interface(bus.get_object("org.bluez", "/"), "org.freedesktop.DBus.ObjectManager")
for path, ifaces in om.GetManagedObjects().items():
    d = ifaces.get("org.bluez.Device1")
    if d and NAME_MATCH in str(d.get("Name", d.get("Alias", ""))).upper():
        log(f"removing stale device {d.get('Address')} (Paired={bool(d.get('Paired'))})")
        adapter.RemoveDevice(path)

adapter.SetDiscoveryFilter({"Transport": dbus.String("le"), "DuplicateData": dbus.Boolean(True)})
adapter.StartDiscovery()
log(f"scanning; waiting up to {WAIT_ADV}s for '{NAME_MATCH}'")
GLib.timeout_add_seconds(WAIT_ADV, no_adv)
GLib.timeout_add_seconds(WAIT_ADV + PAIR_WAIT + STABLE_WATCH + 120, lambda: finish("overall timeout"))
loop.run()
if state['path'] and not state['paired']:
    try:
        adapter.RemoveDevice(state['path']); log('cleanup: removed device')
    except dbus.DBusException as e:
        log(f'cleanup: {e.get_dbus_name()}')
try:
    mgr.UnregisterAgent(AGENT_PATH)
except dbus.DBusException:
    pass
