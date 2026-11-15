"""Energía: batería, perfil de energía, tapa, botón de encendido y suspensión."""
import glob

from gi.repository import Gio, GLib, Gtk

from .ui import Page, kv_grid, seconds_options
from .util import read, root_async, run, settings

ACTIONS = [("suspend", "Suspender"), ("hibernate", "Hibernar"), ("blank", "Apagar la pantalla"),
           ("shutdown", "Apagar el equipo"), ("interactive", "Preguntar"), ("nothing", "No hacer nada")]
LOGIND_ACTIONS = [("suspend", "Suspender"), ("hibernate", "Hibernar"), ("lock", "Bloquear"),
                  ("poweroff", "Apagar"), ("ignore", "No hacer nada")]
LOGIND_DEFAULTS = {"HandleLidSwitch": "suspend", "HandleLidSwitchExternalPower": None,
                   "HandleLidSwitchDocked": "ignore"}
STATES = {0: "Desconocido", 1: "Cargando", 2: "Descargando", 3: "Vacía", 4: "Cargada",
          5: "Pendiente de carga", 6: "Pendiente de descarga"}
PROFILE_NAMES = {"performance": "Rendimiento", "balanced": "Equilibrado", "power-saver": "Ahorro de energía"}


def logind_current():
    cfg = {}
    files = ["/etc/systemd/logind.conf"] + sorted(glob.glob("/etc/systemd/logind.conf.d/*.conf"))
    for path in files:
        for line in (read(path, "") or "").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith(("#", ";")):
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    out = {}
    for k, d in LOGIND_DEFAULTS.items():
        out[k] = cfg.get(k) or d or cfg.get("HandleLidSwitch", "suspend")
    return out


def fmt_time(secs):
    # upower da valores absurdos (días) con la batería llena y el cargador puesto
    if not secs or secs > 48 * 3600:
        return "—"
    h, m = divmod(int(secs) // 60, 60)
    return f"{h} h {m:02d} min" if h else f"{m} min"


class EnergiaPage(Page):
    title = "Energía"
    icon = "battery"

    def __init__(self, win):
        super().__init__(win)
        power = settings("org.cinnamon.settings-daemon.plugins.power")

        # ---------- batería ----------
        self.section("Batería")
        self.level = Gtk.LevelBar(min_value=0, max_value=100)
        self.level.set_size_request(-1, 18)
        self.put(self.level)
        self.bat_grid, self.bat = kv_grid([(k, "—") for k in (
            "Estado", "Carga", "Tiempo restante", "Consumo", "Salud (capacidad)", "Ciclos", "Modelo",
            "Cargador")])
        self.put(self.bat_grid)

        # ---------- perfil ----------
        self.section("Modo de energía", "power-profiles-daemon")
        profiles = [ln.strip().rstrip(":").lstrip("* ") for ln in run(["powerprofilesctl", "list"]).splitlines()
                    if ln.strip().endswith(":") and not ln.startswith(" " * 4)]
        self.profile_radios = {}
        group = None
        pbox = Gtk.Box(spacing=12)
        for p in profiles:
            r = Gtk.RadioButton.new_with_label_from_widget(group, PROFILE_NAMES.get(p, p))
            group = group or r
            r.connect("toggled", self._on_profile, p)
            pbox.pack_start(r, False, False, 0)
            self.profile_radios[p] = r
        if profiles:
            self.put(pbox)
        else:
            self.put(Gtk.Label(label="power-profiles-daemon no disponible", xalign=0))

        # ---------- tapa ----------
        self.section("Al cerrar la tapa", "Con la sesión iniciada lo gestiona Cinnamon")
        self.gs_combo(power, "lid-close-battery-action", "Con batería", ACTIONS)
        self.gs_combo(power, "lid-close-ac-action", "Enchufado", ACTIONS)
        self.gs_switch(power, "lid-close-suspend-with-external-monitor",
                       "Suspender aunque haya un monitor externo",
                       "Desactívalo para usar la Mac cerrada con monitor (modo clamshell)")
        self.gs_switch(power, "lock-on-suspend", "Bloquear la pantalla al suspender")

        self.section("Tapa sin sesión iniciada (systemd-logind)",
                     "Se usa en la pantalla de inicio de sesión. Requiere contraseña de administrador.")
        cur = logind_current()
        self.logind_combos = {}
        for key, label in (("HandleLidSwitch", "Con batería"),
                           ("HandleLidSwitchExternalPower", "Enchufado"),
                           ("HandleLidSwitchDocked", "Con monitor externo")):
            c = Gtk.ComboBoxText()
            for v, txt in LOGIND_ACTIONS:
                c.append(v, txt)
            if not c.set_active_id(cur[key]):
                c.append(cur[key], cur[key])
                c.set_active_id(cur[key])
            self.row(label, None, c)
            self.logind_combos[key] = c
        b = Gtk.Button(label="Aplicar a logind")
        b.set_halign(Gtk.Align.START)
        b.connect("clicked", self._apply_logind)
        self.put(b)

        # ---------- botones y suspensión ----------
        self.section("Botón de encendido y suspensión")
        self.gs_combo(power, "button-power", "Al pulsar el botón de encendido", ACTIONS)
        self.gs_combo(power, "sleep-inactive-battery-timeout", "Suspender por inactividad (batería)",
                      seconds_options())
        self.gs_combo(power, "sleep-inactive-ac-timeout", "Suspender por inactividad (enchufado)",
                      seconds_options())

        self.section("Batería baja")
        self.gs_combo(power, "percentage-low", "Aviso de batería baja",
                      [(v, f"{v} %") for v in (5, 10, 15, 20, 25)])
        self.gs_combo(power, "percentage-critical", "Batería crítica",
                      [(v, f"{v} %") for v in (2, 3, 4, 5, 8, 10)])
        self.gs_combo(power, "critical-battery-action", "Acción en batería crítica", ACTIONS)
        self.refresh()

    def _on_profile(self, r, profile):
        if r.get_active() and not self._busy:
            run(["powerprofilesctl", "set", profile])

    def _apply_logind(self, _):
        args = ["logind"] + [f"{k}={c.get_active_id()}" for k, c in self.logind_combos.items()]
        root_async(args, lambda ok, msg: self.message(
            "logind actualizado" if ok else "No se pudo aplicar", error=not ok, secondary=msg))

    def _upower(self, path, iface="org.freedesktop.UPower.Device"):
        try:
            return Gio.DBusProxy.new_for_bus_sync(Gio.BusType.SYSTEM, Gio.DBusProxyFlags.NONE, None,
                                                  "org.freedesktop.UPower", path, iface, None)
        except GLib.Error:
            return None

    def refresh(self):
        bat = self._upower("/org/freedesktop/UPower/devices/battery_BAT0")
        ac = self._upower("/org/freedesktop/UPower/devices/line_power_ADP1")

        def g(proxy, name, default=None):
            v = proxy.get_cached_property(name) if proxy else None
            return v.unpack() if v is not None else default

        if bat and g(bat, "IsPresent", False):
            pct = g(bat, "Percentage", 0)
            state = g(bat, "State", 0)
            self.level.set_value(pct)
            self.bat["Estado"].set_text(STATES.get(state, "?"))
            self.bat["Carga"].set_text(f"{pct:.0f} %  ({g(bat, 'Energy', 0):.1f} / {g(bat, 'EnergyFull', 0):.1f} Wh)")
            t = g(bat, "TimeToFull") if state == 1 else g(bat, "TimeToEmpty")
            self.bat["Tiempo restante"].set_text(fmt_time(t))
            self.bat["Consumo"].set_text(f"{g(bat, 'EnergyRate', 0):.1f} W")
            cap = g(bat, "Capacity", 0)
            design = g(bat, "EnergyFullDesign", 0)
            self.bat["Salud (capacidad)"].set_text(f"{cap:.0f} %  (diseño {design:.1f} Wh)")
            cycles = g(bat, "ChargeCycles", -1)
            self.bat["Ciclos"].set_text(str(cycles) if cycles and cycles > 0 else "—")
            self.bat["Modelo"].set_text(f"{g(bat, 'Vendor', '')} {g(bat, 'Model', '')}".strip())
        else:
            self.bat["Estado"].set_text("Sin batería")
        self.bat["Cargador"].set_text("Conectado" if g(ac, "Online", False) else "Desconectado")

        cur = run(["powerprofilesctl", "get"]).strip()
        if cur in self.profile_radios:
            self._busy = True
            self.profile_radios[cur].set_active(True)
            self._busy = False
