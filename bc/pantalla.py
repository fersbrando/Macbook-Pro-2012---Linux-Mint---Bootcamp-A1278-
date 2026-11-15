"""Pantalla: brillo (intel_backlight), luz nocturna, atenuado y apagado."""
from gi.repository import Gtk

from .ui import Page, seconds_options
from .util import screen_brightness, settings


class PantallaPage(Page):
    title = "Pantalla"
    icon = "video-display"

    def __init__(self, win):
        super().__init__(win)
        self.scr = screen_brightness()
        power = settings("org.cinnamon.settings-daemon.plugins.power")
        color = settings("org.cinnamon.settings-daemon.plugins.color")
        session = settings("org.cinnamon.desktop.session")
        saver = settings("org.cinnamon.desktop.screensaver")

        dev = self.scr.dev.rsplit("/", 1)[-1] if self.scr.dev else "no encontrado"
        self.section("Brillo", f"Retroiluminación: {dev}")
        self.bright = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 1, 100, 1)
        self.bright.set_size_request(280, -1)
        self.bright.set_value_pos(Gtk.PositionType.RIGHT)
        self.bright.connect("format-value", lambda s, v: f"{int(v)} %")
        self.bright.set_value(self.scr.get())
        self.bright.set_sensitive(self.scr.available)
        self.bright.connect("value-changed", self._on_bright)
        self.row("Brillo de la pantalla", None, self.bright)

        self.section("Luz nocturna", "Reduce la luz azul por la noche")
        self.gs_switch(color, "night-light-enabled", "Activar luz nocturna")
        self.gs_scale(color, "night-light-temperature", "Temperatura de color", 1700, 4700, 100,
                      "Más cálida ← → Más fría", fmt=lambda v: f"{int(v)} K")
        self.gs_combo(color, "night-light-schedule-mode", "Horario", [
            ("auto", "Del atardecer al amanecer"),
            ("manual", "Horario personalizado"),
            ("always", "Siempre"),
        ])
        hours = [(h, f"{int(h):02d}:{int(h % 1 * 60):02d}") for h in [x / 2 for x in range(48)]]
        for key, label in (("night-light-schedule-from", "Desde"), ("night-light-schedule-to", "Hasta")):
            self._hour_combo(color, key, label, hours)

        self.section("Atenuar y apagar")
        self.gs_switch(power, "idle-dim-battery", "Atenuar en inactividad (batería)")
        self.gs_switch(power, "idle-dim-ac", "Atenuar en inactividad (enchufado)")
        self.gs_scale(power, "idle-brightness", "Brillo atenuado", 0, 100, 5, fmt=lambda v: f"{int(v)} %")
        self.gs_combo(power, "idle-dim-time", "Atenuar tras",
                      [(30, "30 s"), (60, "1 min"), (90, "90 s"), (120, "2 min"), (300, "5 min")])
        self.gs_combo(power, "sleep-display-battery", "Apagar pantalla (batería)", seconds_options())
        self.gs_combo(power, "sleep-display-ac", "Apagar pantalla (enchufado)", seconds_options())

        self.section("Bloqueo de pantalla")
        self.gs_combo(session, "idle-delay", "Considerar inactivo tras", seconds_options())
        self.gs_switch(saver, "lock-enabled", "Bloquear al activarse el salvapantallas")
        self.gs_combo(saver, "lock-delay", "Retraso del bloqueo",
                      [(0, "Inmediato"), (30, "30 s"), (60, "1 min"), (300, "5 min")])

    def _hour_combo(self, gs, key, label, hours):
        combo = Gtk.ComboBoxText()
        for h, txt in hours:
            combo.append(str(h), txt)
        if gs:
            cur = round(gs.get_double(key) * 2) / 2
            combo.set_active_id(str(cur))
            combo.connect("changed", lambda c: gs.set_double(key, float(c.get_active_id())))
        else:
            combo.set_sensitive(False)
        self.row(label, None, combo)

    def _on_bright(self, s):
        if not self._busy:
            self.touch()
            self.scr.set(s.get_value())

    def refresh(self):
        if self.scr.available and self.idle():
            self._busy = True
            self.bright.set_value(self.scr.get())
            self._busy = False
