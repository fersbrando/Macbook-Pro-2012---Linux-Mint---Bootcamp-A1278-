#!/usr/bin/env python3
"""
Boot Camp para Linux — panel de control para MacBook (probado en MacBook Pro 9,2 / A1278).

Uso:
  bootcamp                 abre el panel
  bootcamp --page sonido   abre directamente en una pestaña
  bootcamp --apply         reaplica los ajustes del trackpad (se usa al iniciar sesión)
"""
import os
import sys

APP_DIR = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, APP_DIR)

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib, Gtk  # noqa: E402

VERSION = "1.0.0"
ICON = os.path.join(APP_DIR, "icono.png")


def build_pages():
    from bc.energia import EnergiaPage
    from bc.pantalla import PantallaPage
    from bc.sistema import SistemaPage
    from bc.sonido import SonidoPage
    from bc.teclado import TecladoPage
    from bc.trackpad import TrackpadPage
    from bc.ventilador import VentiladorPage
    return [("trackpad", TrackpadPage), ("teclado", TecladoPage), ("sonido", SonidoPage),
            ("pantalla", PantallaPage), ("ventilador", VentiladorPage), ("energia", EnergiaPage),
            ("sistema", SistemaPage)]


class BootCampWindow(Gtk.ApplicationWindow):
    def __init__(self, app, start_page=None):
        super().__init__(application=app, title="Boot Camp")
        self.script = os.path.realpath(__file__)
        self.set_default_size(900, 680)
        if os.path.exists(ICON):
            self.set_icon_from_file(ICON)

        header = Gtk.HeaderBar(title="Boot Camp", subtitle="Panel de control de la Mac")
        header.set_show_close_button(True)
        about = Gtk.Button.new_from_icon_name("help-about-symbolic", Gtk.IconSize.BUTTON)
        about.connect("clicked", self.on_about)
        header.pack_end(about)
        self.set_titlebar(header)

        self.stack = Gtk.Stack(transition_type=Gtk.StackTransitionType.CROSSFADE, hhomogeneous=False)
        sidebar = Gtk.StackSidebar(stack=self.stack)
        sidebar.set_size_request(170, -1)
        self.pages = {}
        for key, cls in build_pages():
            try:
                page = cls(self)
            except Exception as e:  # una pestaña rota no debe tumbar toda la app
                page = Gtk.Label(label=f"Error al cargar «{key}»:\n{e}")
                page.refresh = lambda: None
            self.pages[key] = page
            self.stack.add_titled(page, key, getattr(cls, "title", key))
            self.stack.child_set_property(page, "icon-name", getattr(cls, "icon", None))

        box = Gtk.Box()
        box.pack_start(sidebar, False, False, 0)
        box.pack_start(Gtk.Separator(orientation=Gtk.Orientation.VERTICAL), False, False, 0)
        box.pack_start(self.stack, True, True, 0)
        self.add(box)
        self.show_all()
        self.stack.connect("notify::visible-child", lambda *_: self.tick(once=True))
        if start_page in self.pages:
            self.stack.set_visible_child_name(start_page)
        GLib.timeout_add_seconds(2, self.tick)

    def icon_pixbuf(self, size):
        try:
            return GdkPixbuf.Pixbuf.new_from_file_at_size(ICON, size, size)
        except GLib.Error:
            return None

    def tick(self, once=False):
        page = self.stack.get_visible_child()
        if page is not None and hasattr(page, "refresh"):
            try:
                page.refresh()
            except Exception as e:  # noqa: BLE001
                print(f"refresh: {e}", file=sys.stderr)
        return not once

    def on_about(self, _):
        d = Gtk.AboutDialog(transient_for=self, modal=True, program_name="Boot Camp para Linux",
                            version=VERSION, logo=self.icon_pixbuf(128),
                            comments="Trackpad, teclado, sonido, pantalla, ventilador, energía y "
                                     "drivers de tu MacBook en un solo lugar.",
                            website="https://github.com/fersbrando/Macbook-Pro-2012---Linux-Mint---Bootcamp-A1278-",
                            license_type=Gtk.License.MIT_X11)
        d.run()
        d.destroy()


class BootCampApp(Gtk.Application):
    def __init__(self, start_page):
        super().__init__(application_id="io.github.fersbrando.BootCamp")
        self.start_page = start_page

    def do_activate(self):
        win = self.get_active_window() or BootCampWindow(self, self.start_page)
        win.present()


def main():
    if "--apply" in sys.argv:
        from bc.trackpad import apply_extras, load_extras
        apply_extras(load_extras())
        return
    page = None
    if "--page" in sys.argv:
        i = sys.argv.index("--page")
        page = sys.argv[i + 1] if i + 1 < len(sys.argv) else None
    GLib.set_prgname("bootcamp")
    BootCampApp(page).run([sys.argv[0]])


if __name__ == "__main__":
    main()
