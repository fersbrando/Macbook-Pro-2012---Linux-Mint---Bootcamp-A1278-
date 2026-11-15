"""Teclado: retroiluminación (applesmc) y teclas de función (hid_apple)."""
from gi.repository import Gtk

from .ui import Page
from .util import keyboard_brightness, read, root_async, settings

HID = "/sys/module/hid_apple/parameters/"


class TecladoPage(Page):
    title = "Teclado"
    icon = "input-keyboard"

    def __init__(self, win):
        super().__init__(win)
        self.kbd = keyboard_brightness()

        self.section("Retroiluminación", "LED del teclado controlado por el SMC (driver applesmc)")
        self.light = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 100, 5)
        self.light.set_size_request(260, -1)
        self.light.set_value_pos(Gtk.PositionType.RIGHT)
        self.light.connect("format-value", lambda s, v: f"{int(v)} %")
        self.light.set_value(self.kbd.get())
        self.light.set_sensitive(self.kbd.available)
        self.light.connect("value-changed", self._on_light)
        self.row("Brillo del teclado", None if self.kbd.available else "No se encontró smc::kbd_backlight",
                 self.light)
        power = settings("org.cinnamon.settings-daemon.plugins.power")
        self.gs_switch(power, "power-notifications-for-keyboard", "Avisos de batería de teclados inalámbricos")

        self.section("Teclas de función (hid_apple)",
                     "Solo afecta al teclado Apple integrado. Requiere contraseña de administrador; "
                     "el cambio se aplica al instante y se mantiene tras reiniciar.")
        self.fnmode = Gtk.ComboBoxText()
        for v, label in (("3", "Automático (predeterminado)"),
                         ("1", "Teclas multimedia primero (Fn+F1 = F1)"),
                         ("2", "Teclas F1–F12 primero, como en Windows"),
                         ("0", "Desactivar la tecla Fn")):
            self.fnmode.append(v, label)
        self.fnmode.set_active_id(read(HID + "fnmode", "3"))
        self.row("Modo de las teclas F1–F12", "Igual que la opción de Boot Camp en Windows", self.fnmode)

        self.swap_opt = Gtk.Switch(active=read(HID + "swap_opt_cmd", "0") == "1")
        self.row("Intercambiar Option y Command",
                 "Deja Alt junto a la barra espaciadora, como en un teclado de PC", self.swap_opt)
        self.swap_fn = Gtk.Switch(active=read(HID + "swap_fn_leftctrl", "0") == "1")
        self.row("Intercambiar Fn y Ctrl izquierdo", "Ctrl queda en la esquina, como en un PC", self.swap_fn)

        self.apply_btn = Gtk.Button(label="Aplicar cambios del teclado")
        self.apply_btn.get_style_context().add_class("suggested-action")
        self.apply_btn.set_halign(Gtk.Align.START)
        self.apply_btn.connect("clicked", self._apply_hid)
        self.status = Gtk.Label(xalign=0)
        box = Gtk.Box(spacing=12)
        box.pack_start(self.apply_btn, False, False, 0)
        box.pack_start(self.status, False, False, 0)
        self.put(box)

    def _on_light(self, s):
        if not self._busy:
            self.touch()
            self.kbd.set(s.get_value())

    def _apply_hid(self, _):
        args = ["hid_apple", f"fnmode={self.fnmode.get_active_id()}",
                f"swap_opt_cmd={int(self.swap_opt.get_active())}",
                f"swap_fn_leftctrl={int(self.swap_fn.get_active())}"]
        self.apply_btn.set_sensitive(False)
        self.status.set_text("Aplicando… (regenerar el initramfs tarda ~1 minuto)")

        def done(ok, msg):
            self.apply_btn.set_sensitive(True)
            self.status.set_text("✔ Aplicado" if ok else "")
            if not ok:
                self.message("No se pudo aplicar", error=True, secondary=msg)
        root_async(args, done)

    def refresh(self):
        if self.kbd.available and self.idle():
            self._busy = True
            self.light.set_value(self.kbd.get())
            self._busy = False
