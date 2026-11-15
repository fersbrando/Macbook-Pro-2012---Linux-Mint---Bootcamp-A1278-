"""Bloques de interfaz reutilizables para todas las pestañas."""
import time

from gi.repository import GLib, Gtk


class Page(Gtk.ScrolledWindow):
    """Pestaña base: lista vertical de secciones y filas (estilo Preferencias del Sistema)."""

    title = ""
    icon = "preferences-system"

    def __init__(self, win):
        super().__init__()
        self.win = win
        self.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self.box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4,
                           margin_start=24, margin_end=24, margin_top=12, margin_bottom=24)
        self.add(self.box)
        self._busy = False  # evita bucles al actualizar widgets desde refresh()
        self._touched = 0.0

    def touch(self):
        """Marca que el usuario acaba de mover un control (refresh() no lo pisa)."""
        self._touched = time.monotonic()

    def idle(self, secs=2.0):
        return time.monotonic() - self._touched > secs

    # ---------- estructura ----------
    def section(self, title, subtitle=None):
        lbl = Gtk.Label(xalign=0, margin_top=14)
        lbl.set_markup(f"<b>{GLib.markup_escape_text(title)}</b>")
        self.box.pack_start(lbl, False, False, 0)
        if subtitle:
            s = Gtk.Label(xalign=0, wrap=True)
            s.set_markup(f"<small>{GLib.markup_escape_text(subtitle)}</small>")
            s.get_style_context().add_class("dim-label")
            self.box.pack_start(s, False, False, 0)
        self.box.pack_start(Gtk.Separator(), False, False, 2)

    def row(self, title, subtitle, widget, expand_widget=False):
        h = Gtk.Box(spacing=12)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        v.pack_start(Gtk.Label(label=title, xalign=0), False, False, 0)
        if subtitle:
            s = Gtk.Label(xalign=0, wrap=True, max_width_chars=50)
            s.set_markup(f"<small>{GLib.markup_escape_text(subtitle)}</small>")
            s.get_style_context().add_class("dim-label")
            v.pack_start(s, False, False, 0)
        h.pack_start(v, not expand_widget, True, 0)
        if widget is not None:
            widget.set_valign(Gtk.Align.CENTER)
            h.pack_end(widget, expand_widget, expand_widget, 0)
        self.box.pack_start(h, False, False, 4)
        return h

    def put(self, widget, expand=False):
        self.box.pack_start(widget, expand, expand, 4)
        return widget

    # ---------- widgets ligados a gsettings ----------
    def gs_switch(self, gs, key, title, subtitle=""):
        sw = Gtk.Switch()
        if gs and key in gs.list_keys():
            sw.set_active(gs.get_boolean(key))
            sw.connect("notify::active", lambda w, _: gs.set_boolean(key, w.get_active()))
        else:
            sw.set_sensitive(False)
        self.row(title, subtitle, sw)
        return sw

    def gs_combo(self, gs, key, title, options, subtitle=""):
        """options: [(valor, etiqueta)]. Sirve para claves string/enum y numéricas."""
        combo = Gtk.ComboBoxText()
        if not gs or key not in gs.list_keys():
            for _, label in options:
                combo.append_text(label)
            combo.set_sensitive(False)
            self.row(title, subtitle, combo)
            return combo
        vtype = gs.get_value(key).get_type_string()
        current = gs.get_value(key).unpack()
        ids = [str(v) for v, _ in options]
        for v, label in options:
            combo.append(str(v), label)
        if str(current) not in ids:
            combo.append(str(current), f"Personalizado ({current})")
        combo.set_active_id(str(current))

        def changed(c):
            val = c.get_active_id()
            if val is None:
                return
            if vtype == "s":
                gs.set_string(key, val)
            else:
                gs.set_value(key, GLib.Variant(vtype, int(val)))
        combo.connect("changed", changed)
        self.row(title, subtitle, combo)
        return combo

    def gs_scale(self, gs, key, title, lo, hi, step, subtitle="", fmt=None, width=240):
        scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, lo, hi, step)
        scale.set_size_request(width, -1)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        if fmt:
            scale.connect("format-value", lambda s, v: fmt(v))
        else:
            scale.set_draw_value(False)
        if gs and key in gs.list_keys():
            vtype = gs.get_value(key).get_type_string()
            scale.set_value(gs.get_value(key).unpack())

            def changed(s):
                v = s.get_value()
                gs.set_value(key, GLib.Variant(vtype, v if vtype == "d" else int(round(v))))
            scale.connect("value-changed", changed)
        else:
            scale.set_sensitive(False)
        self.row(title, subtitle, scale)
        return scale

    # ---------- utilidades ----------
    def message(self, text, error=False, secondary=None):
        d = Gtk.MessageDialog(transient_for=self.win,
                              message_type=Gtk.MessageType.ERROR if error else Gtk.MessageType.INFO,
                              buttons=Gtk.ButtonsType.OK, text=text)
        if secondary:
            d.format_secondary_text(secondary)
        d.run()
        d.destroy()

    def refresh(self):
        """Se llama periódicamente mientras la pestaña está visible."""


def kv_grid(rows):
    """Grilla clave/valor de solo lectura. Devuelve (grid, dict de labels por clave)."""
    grid = Gtk.Grid(column_spacing=18, row_spacing=6, margin_top=6)
    labels = {}
    for i, (k, v) in enumerate(rows):
        kl = Gtk.Label(label=k, xalign=1)
        kl.get_style_context().add_class("dim-label")
        vl = Gtk.Label(label=str(v), xalign=0, selectable=True, wrap=True)
        grid.attach(kl, 0, i, 1, 1)
        grid.attach(vl, 1, i, 1, 1)
        labels[k] = vl
    return grid, labels


def seconds_options(include_never=True):
    opts = [(0, "Nunca")] if include_never else []
    for s in (60, 120, 300, 600, 900, 1200, 1800, 2700, 3600, 7200):
        opts.append((s, f"{s // 60} min" if s < 3600 else f"{s // 3600} h"))
    return opts
