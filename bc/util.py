"""Utilidades compartidas: comandos, sysfs, gsettings, D-Bus y helper root (pkexec)."""
import glob
import os
import subprocess

from gi.repository import Gio, GLib

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HELPER = os.path.join(APP_DIR, "bc_helper.py")
ENV_C = {**os.environ, "LANG": "C", "LC_ALL": "C"}


def run(cmd, timeout=6):
    """Ejecuta un comando con locale C y devuelve stdout ('' si falla)."""
    try:
        return subprocess.run(cmd, capture_output=True, text=True, env=ENV_C,
                              timeout=timeout, check=False).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def read(path, default=None):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return default


def first(pattern):
    m = sorted(glob.glob(pattern))
    return m[0] if m else None


def settings(schema_id):
    src = Gio.SettingsSchemaSource.get_default()
    return Gio.Settings.new(schema_id) if src and src.lookup(schema_id, True) else None


# --------------------------------------------------------------------------- #
#  Helper root vía pkexec (asíncrono para no congelar la ventana)
# --------------------------------------------------------------------------- #
def root_async(args, callback):
    """Ejecuta bc_helper.py como root. callback(ok: bool, mensaje: str)."""
    try:
        # Se ejecuta el helper directamente (shebang) para que coincida con la política
        # polkit io.github.fersbrando.bootcamp instalada en /usr/share/polkit-1/actions
        proc = Gio.Subprocess.new(["pkexec", HELPER, *map(str, args)],
                                  Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE)
    except GLib.Error as e:
        callback(False, e.message)
        return

    def done(p, res):
        try:
            _, out, _ = p.communicate_utf8_finish(res)
        except GLib.Error as e:
            callback(False, e.message)
            return
        code = p.get_exit_status()
        if code in (126, 127):
            callback(False, "Autorización cancelada.")
        else:
            callback(code == 0, (out or "").strip())

    proc.communicate_utf8_async(None, None, done)


# --------------------------------------------------------------------------- #
#  Brillo (pantalla y teclado) a través de cinnamon-settings-daemon
# --------------------------------------------------------------------------- #
CSD_NAME = "org.cinnamon.SettingsDaemon.Power"
CSD_PATH = "/org/cinnamon/SettingsDaemon/Power"


class Brightness:
    """kind = 'Screen' o 'Keyboard'. Lee de sysfs y escribe vía D-Bus (sin root)."""

    def __init__(self, kind, sysfs_glob, logind_subsystem):
        self.kind = kind
        self.dev = first(sysfs_glob)
        self.logind_subsystem = logind_subsystem
        try:
            self.session = Gio.bus_get_sync(Gio.BusType.SESSION)
            self.system = Gio.bus_get_sync(Gio.BusType.SYSTEM)
        except GLib.Error:
            self.session = self.system = None

    @property
    def available(self):
        return self.dev is not None

    def get(self):
        if not self.dev:
            return 0
        cur = int(read(self.dev + "/brightness", "0"))
        mx = int(read(self.dev + "/max_brightness", "1")) or 1
        return round(cur * 100 / mx)

    def set(self, pct):
        pct = int(max(0, min(100, pct)))
        try:
            self.session.call_sync(CSD_NAME, CSD_PATH, f"{CSD_NAME}.{self.kind}", "SetPercentage",
                                   GLib.Variant("(u)", (pct,)), None, Gio.DBusCallFlags.NONE, 1000, None)
            return
        except (GLib.Error, AttributeError):
            pass
        # Alternativa: logind permite al usuario de la sesión activa cambiar el brillo
        try:
            mx = int(read(self.dev + "/max_brightness", "1"))
            self.system.call_sync("org.freedesktop.login1", "/org/freedesktop/login1/session/auto",
                                  "org.freedesktop.login1.Session", "SetBrightness",
                                  GLib.Variant("(ssu)", (self.logind_subsystem,
                                                         os.path.basename(self.dev),
                                                         round(pct * mx / 100))),
                                  None, Gio.DBusCallFlags.NONE, 1000, None)
        except (GLib.Error, AttributeError, TypeError):
            pass


def screen_brightness():
    return Brightness("Screen", "/sys/class/backlight/*", "backlight")


def keyboard_brightness():
    return Brightness("Keyboard", "/sys/class/leds/*kbd_backlight*", "leds")
