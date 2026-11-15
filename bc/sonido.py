"""Sonido: salida/entrada vía pactl (PipeWire o PulseAudio)."""
import re

from gi.repository import Gtk

from .ui import Page
from .util import read, run, settings


def list_devices(kind):
    """kind = 'sinks' | 'sources'. Devuelve [{name, desc, mute, vol}] (sin monitores)."""
    devs, cur = [], None
    for line in run(["pactl", "list", kind]).splitlines():
        s = line.strip()
        if re.match(r"^(Sink|Source) #\d+", line):
            cur = {"name": "", "desc": "", "mute": False, "vol": 0}
            devs.append(cur)
        elif cur is None:
            continue
        elif s.startswith("Name:"):
            cur["name"] = s.split(":", 1)[1].strip()
        elif s.startswith("Description:"):
            cur["desc"] = s.split(":", 1)[1].strip()
        elif s.startswith("Mute:"):
            cur["mute"] = s.endswith("yes")
        elif s.startswith("Volume:") and not cur["vol"]:
            m = re.search(r"/\s*(\d+)%", s)
            cur["vol"] = int(m.group(1)) if m else 0
    return [d for d in devs if d["name"] and not d["name"].endswith(".monitor")]


class Channel:
    """Bloque de controles para la salida o la entrada."""

    def __init__(self, page, kind, title, max_vol):
        self.page, self.kind = page, kind
        self.target = "sink" if kind == "sinks" else "source"
        page.section(title)
        self.combo = Gtk.ComboBoxText()
        self.combo.set_size_request(260, -1)
        self.combo.connect("changed", self._on_device)
        page.row("Dispositivo", None, self.combo)

        self.scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, max_vol, 1)
        self.scale.set_size_request(260, -1)
        self.scale.set_value_pos(Gtk.PositionType.RIGHT)
        self.scale.connect("format-value", lambda s, v: f"{int(v)} %")
        self.scale.add_mark(100, Gtk.PositionType.BOTTOM, None)
        self.scale.connect("value-changed", self._on_volume)
        page.row("Volumen", None, self.scale)

        self.mute = Gtk.Switch()
        self.mute.connect("notify::active", self._on_mute)
        page.row("Silenciar", None, self.mute)

    def _on_device(self, c):
        if not self.page._busy and c.get_active_id():
            self.page.touch()
            run(["pactl", f"set-default-{self.target}", c.get_active_id()])

    def _on_volume(self, s):
        if not self.page._busy:
            self.page.touch()
            run(["pactl", f"set-{self.target}-volume", f"@DEFAULT_{self.target.upper()}@",
                 f"{int(s.get_value())}%"])

    def _on_mute(self, w, _):
        if not self.page._busy:
            self.page.touch()
            run(["pactl", f"set-{self.target}-mute", f"@DEFAULT_{self.target.upper()}@",
                 "1" if w.get_active() else "0"])

    def refresh(self):
        devs = list_devices(self.kind)
        default = run(["pactl", f"get-default-{self.target}"]).strip()
        ids = [d["name"] for d in devs]
        model_ids = [r[1] for r in self.combo.get_model()] if self.combo.get_model() else []
        if ids != model_ids:
            self.combo.remove_all()
            for d in devs:
                self.combo.append(d["name"], d["desc"] or d["name"])
        self.combo.set_active_id(default)
        cur = next((d for d in devs if d["name"] == default), None)
        if cur:
            self.scale.set_value(cur["vol"])
            self.mute.set_active(cur["mute"])


class SonidoPage(Page):
    title = "Sonido"
    icon = "audio-volume-high"

    def __init__(self, win):
        super().__init__(win)
        snd = settings("org.cinnamon.desktop.sound")
        amplified = bool(snd and snd.get_boolean("allow-amplified-volume"))
        codec = (read("/proc/asound/card0/codec#0", "") or "").splitlines()
        codec = codec[0].replace("Codec:", "").strip() if codec else "desconocido"

        self.out = Channel(self, "sinks", "Salida", 150 if amplified else 100)
        self.inp = Channel(self, "sources", "Entrada (micrófono)", 100)

        self.section("Opciones", f"Códec de audio: {codec} · driver snd_hda_intel + snd_hda_codec_cirrus")
        self.gs_switch(snd, "allow-amplified-volume", "Permitir volumen por encima de 100 %",
                       "Puede distorsionar los parlantes. Reabre Boot Camp para ampliar el control")
        self.gs_switch(snd, "volume-sound-enabled", "Sonido al cambiar el volumen")
        self.gs_switch(snd, "event-sounds", "Sonidos de eventos del sistema")
        self.refresh()

    def refresh(self):
        if not self.idle():
            return
        self._busy = True
        try:
            self.out.refresh()
            self.inp.refresh()
        finally:
            self._busy = False
