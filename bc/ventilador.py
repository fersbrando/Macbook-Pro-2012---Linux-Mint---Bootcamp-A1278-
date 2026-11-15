"""Ventilador: interfaz para el servicio fancontrold (proyecto fancontroler)."""
import math
import os
import sys

from gi.repository import GLib, Gtk

from .ui import Page
from .util import root_async, run

SERVICE = "fancontrold"
for _p in ("/usr/local/lib/fancontrol",
           os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fancontrol")):
    if os.path.exists(os.path.join(_p, "fanlib.py")):
        sys.path.insert(0, _p)
        break
try:
    import fanlib  # noqa: E402
except ImportError:
    fanlib = None


class CurveView(Gtk.DrawingArea):
    """Dibuja la curva temperatura→% y la temperatura actual."""

    T0, T1 = 30, 100

    def __init__(self):
        super().__init__()
        self.set_size_request(-1, 170)
        self.curve, self.temp, self.pct = [], None, None
        self.connect("draw", self.on_draw)

    def update(self, curve, temp, pct):
        self.curve, self.temp, self.pct = curve, temp, pct
        self.queue_draw()

    def on_draw(self, w, cr):
        W, H = w.get_allocated_width(), w.get_allocated_height()
        ml, mb, mt, mr = 36, 22, 8, 24
        pw, ph = W - ml - mr, H - mt - mb
        fg = w.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        X = lambda t: ml + (t - self.T0) / (self.T1 - self.T0) * pw  # noqa: E731
        Y = lambda p: mt + ph - p / 100 * ph  # noqa: E731

        cr.set_font_size(10)
        cr.set_line_width(1)
        for p in (0, 50, 100):
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.15)
            cr.move_to(ml, Y(p)); cr.line_to(ml + pw, Y(p)); cr.stroke()
            cr.set_source_rgba(fg.red, fg.green, fg.blue, 0.6)
            cr.move_to(4, Y(p) + 4); cr.show_text(f"{p}%")
        for t in range(self.T0, self.T1 + 1, 10):
            cr.move_to(X(t) - 8, H - 6); cr.show_text(f"{t}°")
        if len(self.curve) >= 2:
            pts = [(self.T0, self.curve[0][1])] + list(self.curve) + [(self.T1, self.curve[-1][1])]
            cr.set_source_rgb(0.2, 0.55, 0.95)
            cr.set_line_width(2.5)
            cr.move_to(X(pts[0][0]), Y(pts[0][1]))
            for t, p in pts[1:]:
                cr.line_to(X(t), Y(p))
            cr.stroke()
            for t, p in self.curve:
                cr.arc(X(t), Y(p), 4, 0, 2 * math.pi); cr.fill()
        if self.temp:
            t = max(self.T0, min(self.T1, self.temp))
            cr.set_source_rgb(0.95, 0.4, 0.2)
            cr.set_line_width(1.5)
            cr.move_to(X(t), mt); cr.line_to(X(t), mt + ph); cr.stroke()
            if self.pct is not None:
                cr.arc(X(t), Y(self.pct), 5, 0, 2 * math.pi); cr.fill()


class VentiladorPage(Page):
    title = "Ventilador"
    icon = "weather-windy"

    def __init__(self, win):
        super().__init__(win)
        if fanlib is None:
            self.section("Ventilador")
            self.put(Gtk.Label(label="No se encontró fanlib.py del proyecto fancontroler.\n"
                                     "Vuelve a ejecutar install.sh para instalar el servicio fancontrold.", xalign=0))
            self.fans = []
            return
        self.fans = fanlib.find_fans()
        self.cfg = fanlib.load_config()
        self._save_id = 0

        # ---------- servicio ----------
        self.section("Servicio fancontrold", "Controla el ventilador desde /etc/fancontrol/config.json")
        self.svc_label = Gtk.Label(xalign=0)
        btns = Gtk.Box(spacing=6)
        for label, op in (("Iniciar", "start"), ("Detener", "stop"), ("Reiniciar", "restart")):
            b = Gtk.Button(label=label)
            b.connect("clicked", lambda _b, o=op: self._service(o))
            btns.pack_start(b, False, False, 0)
        self.row("Estado", None, btns)
        self.put(self.svc_label)
        self.enabled = Gtk.Switch()
        self.enabled.connect("notify::active", self._on_enable)
        self.row("Iniciar con el sistema", None, self.enabled)

        # ---------- estado en vivo ----------
        self.section("Estado actual")
        self.fan_widgets = []
        for f in self.fans:
            bar = Gtk.LevelBar(min_value=0, max_value=f.max)
            bar.set_size_request(220, 14)
            lbl = Gtk.Label(width_chars=10, xalign=1)
            box = Gtk.Box(spacing=8)
            box.pack_start(bar, True, True, 0)
            box.pack_start(lbl, False, False, 0)
            self.row(f"Ventilador «{f.label}»", f"{f.min}–{f.max} rpm", box)
            self.fan_widgets.append((f, bar, lbl))
        self.cpu_label = Gtk.Label(xalign=1)
        self.row("Temperatura CPU", None, self.cpu_label)
        self.target_label = Gtk.Label(xalign=1)
        self.row("Objetivo del servicio", None, self.target_label)

        # ---------- modo ----------
        self.section("Modo de control")
        self.radios = {}
        group = None
        mode_box = Gtk.Box(spacing=12)
        for mode, label in (("auto", "Automático (SMC de Apple)"), ("curve", "Curva"), ("manual", "Manual")):
            r = Gtk.RadioButton.new_with_label_from_widget(group, label)
            group = group or r
            r.connect("toggled", self._on_mode, mode)
            mode_box.pack_start(r, False, False, 0)
            self.radios[mode] = r
        self.put(mode_box)

        self.manual = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 1)
        self.manual.set_size_request(260, -1)
        self.manual.set_value_pos(Gtk.PositionType.RIGHT)
        self.manual.connect("format-value", lambda s, v: f"{int(v)} %")
        self.manual.set_value(self.cfg["manual_pct"])
        self.manual.connect("value-changed", lambda s: self._set("manual_pct", int(s.get_value())))
        self.manual_row = self.row("Velocidad manual", "0 % = mínimo, 100 % = máximo del ventilador", self.manual)

        # ---------- curva ----------
        self.curve_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.view = CurveView()
        self.curve_box.pack_start(self.view, False, False, 4)
        self.points_grid = Gtk.Grid(column_spacing=10, row_spacing=4)
        self.curve_box.pack_start(self.points_grid, False, False, 0)
        pb = Gtk.Box(spacing=6)
        add = Gtk.Button(label="Añadir punto")
        add.connect("clicked", self._add_point)
        rem = Gtk.Button(label="Quitar último")
        rem.connect("clicked", self._remove_point)
        pb.pack_start(add, False, False, 0)
        pb.pack_start(rem, False, False, 0)
        self.curve_box.pack_start(pb, False, False, 4)
        self.put(self.curve_box)
        self._build_points()

        # ---------- seguridad ----------
        self.section("Seguridad")
        self.row("Aviso en el escritorio a", None, self._spin("alert_temp", 40, 100))
        self.row("Emergencia (fuerza 100 %) a", "Se aplica en cualquier modo", self._spin("emergency_temp", 50, 100))

        # ---------- sensores ----------
        self.section("Sensores de temperatura")
        self.temps_store = Gtk.ListStore(str, str, str)
        tv = Gtk.TreeView(model=self.temps_store, headers_visible=True)
        for i, title in enumerate(("Grupo", "Sensor", "°C")):
            col = Gtk.TreeViewColumn(title, Gtk.CellRendererText(), text=i)
            col.set_expand(i == 1)
            tv.append_column(col)
        self.put(tv)

        self.radios.get(self.cfg["mode"], self.radios["auto"]).set_active(True)
        self._update_mode_visibility()
        self.refresh()

    # ---------- configuración ----------
    def _spin(self, key, lo, hi):
        sp = Gtk.SpinButton.new_with_range(lo, hi, 1)
        sp.set_value(self.cfg[key])
        sp.connect("value-changed", lambda s: self._set(key, s.get_value()))
        box = Gtk.Box(spacing=4)
        box.pack_start(sp, False, False, 0)
        box.pack_start(Gtk.Label(label="°C"), False, False, 0)
        return box

    def _set(self, key, value):
        if self._busy:
            return
        self.touch()
        self.cfg[key] = value
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(400, self._save)

    def _save(self):
        self._save_id = 0
        try:
            fanlib.save_config(self.cfg)
        except OSError as e:
            self.message("No se pudo guardar la configuración", error=True,
                         secondary=f"{e}\n¿Tu usuario está en el grupo sudo?")
        return False

    def _on_mode(self, radio, mode):
        if radio.get_active():
            self._set("mode", mode)
            self._update_mode_visibility()

    def _update_mode_visibility(self):
        mode = self.cfg["mode"]
        for widget, visible in ((self.manual_row, mode == "manual"), (self.curve_box, mode == "curve")):
            # no_show_all evita que el show_all() de la ventana los vuelva a mostrar
            widget.set_no_show_all(False)
            if visible:
                widget.show_all()
            else:
                widget.hide()
            widget.set_no_show_all(True)

    def _build_points(self):
        for c in self.points_grid.get_children():
            self.points_grid.remove(c)
        self.points_grid.attach(Gtk.Label(label="Temperatura", xalign=0), 1, 0, 1, 1)
        self.points_grid.attach(Gtk.Label(label="Velocidad", xalign=0), 2, 0, 1, 1)
        for i, (t, p) in enumerate(self.cfg["curve"]):
            self.points_grid.attach(Gtk.Label(label=f"Punto {i + 1}"), 0, i + 1, 1, 1)
            st = Gtk.SpinButton.new_with_range(20, 105, 1)
            st.set_value(t)
            sp = Gtk.SpinButton.new_with_range(0, 100, 5)
            sp.set_value(p)
            st.connect("value-changed", self._on_point, i, 0)
            sp.connect("value-changed", self._on_point, i, 1)
            self.points_grid.attach(st, 1, i + 1, 1, 1)
            self.points_grid.attach(sp, 2, i + 1, 1, 1)
        self.points_grid.show_all()

    def _on_point(self, spin, i, j):
        curve = [list(pt) for pt in self.cfg["curve"]]
        curve[i][j] = spin.get_value()
        temps = [t for t, _ in curve]
        if temps != sorted(temps) or len(set(temps)) != len(temps):
            spin.get_style_context().add_class("error")
            return  # el servicio rechaza curvas desordenadas: no guardar
        spin.get_style_context().remove_class("error")
        self._set("curve", curve)

    def _add_point(self, _):
        t, p = self.cfg["curve"][-1]
        self._set("curve", [list(pt) for pt in self.cfg["curve"]] + [[min(t + 5, 105), min(p + 10, 100)]])
        self._build_points()

    def _remove_point(self, _):
        if len(self.cfg["curve"]) > 2:
            self._set("curve", [list(pt) for pt in self.cfg["curve"][:-1]])
            self._build_points()

    # ---------- servicio ----------
    def _service(self, op):
        self.svc_label.set_text("Esperando autorización…")
        root_async(["service", SERVICE, op], lambda ok, msg: (
            self.refresh(), None if ok else self.message("Error con el servicio", True, msg)))

    def _on_enable(self, w, _):
        if not self._busy:
            self._service("enable" if w.get_active() else "disable")

    # ---------- refresco ----------
    def refresh(self):
        if not self.fans:
            return
        active = run(["systemctl", "is-active", SERVICE]).strip()
        enabled = run(["systemctl", "is-enabled", SERVICE]).strip()
        st = fanlib.read_status()
        icon = "🟢" if active == "active" else "🔴"
        self.svc_label.set_markup(f"{icon} <b>{active}</b> · arranque: {enabled}")
        self._busy = True
        self.enabled.set_active(enabled == "enabled")
        self._busy = False

        for f, bar, lbl in self.fan_widgets:
            rpm = f.rpm()
            bar.set_value(min(rpm, f.max))
            lbl.set_text(f"{rpm} rpm")
        temps = fanlib.read_temps()
        cpu = fanlib.cpu_temp(temps)
        self.cpu_label.set_markup(f"<b>{cpu:.0f} °C</b>")
        if st:
            tgt = st.get("target_pct")
            txt = "SMC automático" if tgt is None else f"{tgt:.0f} %"
            if st.get("emergency"):
                txt += "  ⚠ EMERGENCIA"
            self.target_label.set_text(txt)
        else:
            tgt = None
            self.target_label.set_text("servicio sin datos")
        self.view.update(self.cfg["curve"], cpu,
                         fanlib.curve_percent(cpu, self.cfg["curve"]) if self.cfg["mode"] == "curve" else None)

        self.temps_store.clear()
        for g, name, c in temps:
            self.temps_store.append([g, name, f"{c:.1f}"])
