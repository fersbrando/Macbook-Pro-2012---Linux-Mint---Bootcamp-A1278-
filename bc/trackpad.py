"""Trackpad: driver bcm5974 + libinput + gsettings de Cinnamon."""
import json
import os

from gi.repository import Gtk

from .ui import Page
from .util import run, settings

SCHEMA = "org.cinnamon.desktop.peripherals.touchpad"
DRIVER = "bcm5974"
CONFIG_DIR = os.path.expanduser("~/.config/bootcamp")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
AUTOSTART = os.path.expanduser("~/.config/autostart/bootcamp.desktop")

DEFAULT_EXTRAS = {
    "accel_profile": "adaptive",  # adaptive | flat
    "scroll_distance": 15,        # libinput Scrolling Pixel Distance (menor = más rápido)
    "drag_lock": False,
}


def find_touchpad():
    names = run(["xinput", "list", "--name-only"]).splitlines()
    for n in names:
        if DRIVER in n:
            return n
    for n in names:
        if "touchpad" in n.lower() or "trackpad" in n.lower():
            return n
    return None


def load_extras():
    try:
        with open(CONFIG_FILE) as f:
            return {**DEFAULT_EXTRAS, **json.load(f)}
    except (OSError, ValueError):
        return dict(DEFAULT_EXTRAS)


def save_extras(extras):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(extras, f, indent=2)


def apply_extras(extras, device=None):
    device = device or find_touchpad()
    if not device:
        return
    profile = ("1", "0", "0") if extras["accel_profile"] == "adaptive" else ("0", "1", "0")
    run(["xinput", "set-prop", device, "libinput Accel Profile Enabled", *profile])
    run(["xinput", "set-prop", device, "libinput Scrolling Pixel Distance",
         str(int(extras["scroll_distance"]))])
    run(["xinput", "set-prop", device, "libinput Tapping Drag Lock Enabled",
         str(int(extras["drag_lock"]))])


def set_autostart(enabled, script):
    if enabled:
        os.makedirs(os.path.dirname(AUTOSTART), exist_ok=True)
        cmd = "bootcamp" if os.path.exists("/usr/local/bin/bootcamp") else f"python3 \"{script}\""
        with open(AUTOSTART, "w") as f:
            f.write("[Desktop Entry]\nType=Application\nName=Boot Camp (trackpad)\n"
                    f"Exec={cmd} --apply\n"
                    "X-GNOME-Autostart-enabled=true\nNoDisplay=true\n")
    elif os.path.exists(AUTOSTART):
        os.remove(AUTOSTART)


class TrackpadPage(Page):
    title = "Trackpad"
    icon = "input-touchpad"

    def __init__(self, win):
        super().__init__(win)
        self.device = find_touchpad()
        self.extras = load_extras()
        gs = self.gs = settings(SCHEMA)

        self.section("General", f"Driver de kernel: {DRIVER} · dispositivo: {self.device or 'no encontrado'}")
        enabled = Gtk.Switch()
        if gs:
            enabled.set_active(gs.get_string("send-events") != "disabled")
            enabled.connect("notify::active", lambda w, _: gs.set_string(
                "send-events", "enabled" if w.get_active() else "disabled"))
        self.row("Trackpad activado", "Desactívalo si usas un ratón externo", enabled)
        self.gs_switch(gs, "disable-while-typing", "Desactivar mientras escribes",
                       "Evita toques accidentales con la palma")

        self.section("Apuntar")
        self.gs_scale(gs, "speed", "Velocidad del puntero", -1.0, 1.0, 0.05, "Lenta ← → Rápida")
        accel = Gtk.ComboBoxText()
        accel.append("adaptive", "Adaptativa (estilo macOS)")
        accel.append("flat", "Plana (sin aceleración)")
        accel.set_active_id(self.extras["accel_profile"])
        accel.connect("changed", lambda c: self._extra("accel_profile", c.get_active_id()))
        self.row("Aceleración", "Cómo crece la velocidad al mover rápido", accel)

        self.section("Clic")
        self.gs_switch(gs, "tap-to-click", "Tocar para hacer clic", "Un toque ligero = clic")
        self.gs_switch(gs, "tap-and-drag", "Tocar y arrastrar", "Doble toque y mantener para arrastrar")
        lock = Gtk.Switch(active=self.extras["drag_lock"])
        lock.connect("notify::active", lambda w, _: self._extra("drag_lock", w.get_active()))
        self.row("Bloqueo de arrastre", "Al levantar el dedo el arrastre continúa un momento", lock)
        self.gs_combo(gs, "click-method", "Clic secundario", [
            ("default", "Predeterminado"),
            ("fingers", "Clic con dos dedos (Mac)"),
            ("areas", "Esquina inferior derecha (Windows)"),
            ("none", "Ninguno"),
        ], "Cómo hacer clic derecho al presionar el trackpad")
        self.gs_switch(gs, "middle-click-emulation", "Emular clic central", "Pulsar izquierdo + derecho a la vez")
        self.gs_combo(gs, "left-handed", "Modo zurdo",
                      [("mouse", "Igual que el ratón"), ("left", "Zurdo"), ("right", "Diestro")])

        self.section("Desplazamiento")
        self.gs_switch(gs, "natural-scroll", "Desplazamiento natural", "El contenido sigue al dedo, como en macOS")
        self.gs_switch(gs, "two-finger-scrolling-enabled", "Desplazar con dos dedos")
        self.gs_switch(gs, "edge-scrolling-enabled", "Desplazar por el borde", "Deslizar un dedo por el borde derecho")
        dist = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 5, 50, 1)
        dist.set_inverted(True)  # menos píxeles por paso = más rápido
        dist.set_draw_value(False)
        dist.set_size_request(240, -1)
        dist.set_value(self.extras["scroll_distance"])
        dist.add_mark(15, Gtk.PositionType.BOTTOM, None)
        dist.connect("value-changed", lambda s: self._extra("scroll_distance", int(s.get_value())))
        self.row("Velocidad de desplazamiento", "Lenta ← → Rápida", dist)

        self.section("Inicio de sesión")
        auto = Gtk.Switch(active=os.path.exists(AUTOSTART))
        auto.connect("notify::active", lambda w, _: set_autostart(w.get_active(), win.script))
        self.row("Aplicar al iniciar sesión",
                 "Aceleración, velocidad de desplazamiento y bloqueo de arrastre no los guarda "
                 "Cinnamon; esto los reaplica automáticamente", auto)

        reset = Gtk.Button(label="Restaurar valores del trackpad")
        reset.set_halign(Gtk.Align.START)
        reset.connect("clicked", self.on_reset)
        self.put(reset)

    def _extra(self, key, value):
        self.extras[key] = value
        save_extras(self.extras)
        apply_extras(self.extras, self.device)

    def on_reset(self, _):
        if self.gs:
            for key in self.gs.list_keys():
                self.gs.reset(key)
        self.extras = dict(DEFAULT_EXTRAS)
        save_extras(self.extras)
        apply_extras(self.extras, self.device)
        self.message("Valores restaurados", secondary="Vuelve a abrir Boot Camp para ver los cambios.")
