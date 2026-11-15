"""Sistema: inventario de componentes de la Mac, drivers y versiones."""
import glob
import os
import platform
import re
import threading

from gi.repository import Gdk, GLib, Gtk, Pango

from .ui import Page
from .util import read, run

MODELS = {
    "MacBookPro9,1": "MacBook Pro (15\", mediados de 2012)",
    "MacBookPro9,2": "MacBook Pro (13\", mediados de 2012) · A1278",
    "MacBookPro8,1": "MacBook Pro (13\", principios/finales de 2011) · A1278",
    "MacBookPro8,2": "MacBook Pro (15\", 2011)",
    "MacBookPro10,1": "MacBook Pro Retina (15\", 2012)",
    "MacBookPro10,2": "MacBook Pro Retina (13\", 2012)",
    "MacBookPro11,1": "MacBook Pro Retina (13\", 2013-2014)",
    "MacBookAir5,2": "MacBook Air (13\", 2012)",
    "MacBookAir6,2": "MacBook Air (13\", 2013-2014)",
    "MacBookAir7,2": "MacBook Air (13\", 2015-2017)",
}

APPLE_MODULES = {
    "applesmc": "Sensores, ventiladores y luz del teclado (SMC)",
    "apple_gmux": "Multiplexor gráfico / retroiluminación",
    "apple_bl": "Retroiluminación Apple (antiguas)",
    "hid_apple": "Teclado Apple (teclas Fn)",
    "hid_appleir": "Receptor infrarrojo (Apple Remote)",
    "bcm5974": "Trackpad multitouch",
    "sbs": "Smart Battery System",
    "snd_hda_codec_cirrus": "Códec de audio Cirrus Logic",
    "wl": "Wi-Fi Broadcom (propietario, broadcom-sta)",
    "b43": "Wi-Fi Broadcom (libre)",
    "brcmfmac": "Wi-Fi Broadcom FullMAC",
    "btusb": "Bluetooth USB",
    "facetimehd": "Cámara FaceTime HD (PCIe)",
    "uvcvideo": "Cámara USB (UVC)",
    "tg3": "Ethernet Broadcom",
    "sdhci_pci": "Lector de tarjetas SD",
    "i915": "Gráficos Intel",
    "nouveau": "Gráficos NVIDIA (libre)",
    "coretemp": "Temperatura de la CPU",
    "thunderbolt": "Thunderbolt",
}

PCI_CATEGORIES = [
    ("VGA", "Gráficos"), ("3D", "Gráficos"), ("Display", "Gráficos"),
    ("Network", "Red"), ("Ethernet", "Red"), ("Audio", "Audio"), ("SD Host", "Almacenamiento"),
    ("SATA", "Almacenamiento"), ("NVMe", "Almacenamiento"), ("Non-Volatile", "Almacenamiento"),
    ("USB", "USB y controladoras"), ("Thunderbolt", "USB y controladoras"),
    ("System peripheral", "Chipset"), ("Bridge", "Chipset"), ("SMBus", "Chipset"),
    ("Communication", "Chipset"), ("Host bridge", "Chipset"), ("FireWire", "USB y controladoras"),
]


class Inventory:
    """Recolecta la información (se ejecuta en un hilo)."""

    def __init__(self):
        self.kernel = platform.release()
        self.loaded = {l.split()[0] for l in run(["lsmod"]).splitlines()[1:] if l.strip()}
        self.dkms = {}
        for line in run(["dkms", "status"]).splitlines():
            m = re.match(r"([^/,]+)/([^,]+),", line)
            if m:
                self.dkms[m.group(1)] = m.group(2)
        self.cats = {}  # categoría -> [(componente, detalle, driver, versión)]

    def add(self, cat, comp, detail="", driver="", version=""):
        self.cats.setdefault(cat, []).append((comp, detail, driver, version))

    def modver(self, mod):
        if not mod:
            return ""
        v = run(["modinfo", "-F", "version", mod]).strip()
        fname = run(["modinfo", "-n", mod]).strip()
        if "dkms" in fname or "updates" in fname:
            for name, ver in self.dkms.items():
                if mod in name or (mod == "wl" and ("broadcom" in name or "bcmwl" in name)):
                    return f"{ver} (DKMS)"
        if v:
            return v
        if fname == "(builtin)" or not fname:
            return f"integrado en kernel {self.kernel}" if mod else ""
        return f"kernel {self.kernel}"

    def collect(self):
        self.equipo()
        self.cpu()
        self.memoria()
        self.pci()
        self.discos()
        self.usb()
        self.audio()
        self.sensores()
        self.bateria()
        self.camara()
        self.modulos()
        return self.cats

    def equipo(self):
        dmi = lambda k: read(f"/sys/class/dmi/id/{k}", "") or ""  # noqa: E731
        model = dmi("product_name")
        self.add("Equipo", "Modelo", MODELS.get(model, model), "", model)
        self.add("Equipo", "Fabricante", dmi("sys_vendor"))
        self.add("Equipo", "Board ID", dmi("board_name"))
        self.add("Equipo", "Firmware (EFI/Boot ROM)", dmi("bios_version"), "", dmi("bios_date"))
        osr = dict(re.findall(r'^(\w+)="?([^"\n]*)"?', read("/etc/os-release", "") or "", re.M))
        self.add("Equipo", "Sistema operativo", osr.get("PRETTY_NAME", "Linux"))
        self.add("Equipo", "Kernel", self.kernel, "", platform.machine())
        de = run(["cinnamon", "--version"]).strip() or os.environ.get("XDG_CURRENT_DESKTOP", "")
        self.add("Equipo", "Escritorio", de, "", os.environ.get("XDG_SESSION_TYPE", ""))
        efi = "UEFI" if os.path.isdir("/sys/firmware/efi") else "BIOS/CSM (Legacy)"
        self.add("Equipo", "Modo de arranque", efi)

    def cpu(self):
        info = dict(re.findall(r"^([^:\n]+?)\s*:\s*(.+)$", run(["lscpu"]), re.M))
        name = info.get("Model name", "?")
        mhz = info.get("CPU max MHz", "")
        detail = f"{info.get('CPU(s)', '?')} hilos · {info.get('Core(s) per socket', '?')} núcleos"
        if mhz:
            detail += f" · hasta {float(mhz) / 1000:.1f} GHz"
        drv = read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver", "")
        gov = read("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor", "")
        self.add("Procesador", name, detail, drv, f"gobernador: {gov}" if gov else "")
        mc = re.search(r"microcode\s*:\s*(\S+)", read("/proc/cpuinfo", "") or "")
        if mc:
            self.add("Procesador", "Microcódigo", "", "intel-microcode", mc.group(1))

    def memoria(self):
        m = re.search(r"MemTotal:\s+(\d+)", read("/proc/meminfo", "") or "")
        total = int(m.group(1)) / 1024 / 1024 if m else 0
        sw = re.search(r"SwapTotal:\s+(\d+)", read("/proc/meminfo", "") or "")
        self.add("Memoria", "RAM", f"{total:.1f} GB", "", "DDR3 1600 MHz" if "MacBookPro9" in
                 (read("/sys/class/dmi/id/product_name", "") or "") else "")
        if sw:
            self.add("Memoria", "Swap", f"{int(sw.group(1)) / 1024 / 1024:.1f} GB")

    def pci(self):
        dev, devices = None, []
        for line in run(["lspci", "-k"]).splitlines():
            if line and not line[0].isspace():
                slot, rest = line.split(" ", 1)
                cls, name = rest.split(": ", 1) if ": " in rest else ("", rest)
                dev = {"slot": slot, "cls": cls, "name": name, "driver": "", "sub": ""}
                cat = next((c for k, c in PCI_CATEGORIES if k in cls), "Otros PCI")
                dev["cat"] = cat
                devices.append(dev)
            elif dev and "Kernel driver in use:" in line:
                dev["driver"] = line.split(":", 1)[1].strip()
            elif dev and "Subsystem:" in line:
                dev["sub"] = line.split(":", 1)[1].strip()
        glx = run(["glxinfo", "-B"])
        renderer = re.search(r"OpenGL renderer string: (.+)", glx)
        glver = re.search(r"OpenGL version string: (.+)", glx)
        for d in devices:
            name = re.sub(r"\s*\(rev \w+\)", "", d["name"])
            detail = d["cls"]
            if "Apple" in d["sub"]:
                detail += f" · {d['sub'].replace('Apple Inc. ', 'Apple ')}"
            self.add(d["cat"], name, detail, d["driver"] or "sin driver", self.modver(d["driver"]))
        if renderer:
            self.add("Gráficos", "OpenGL", renderer.group(1), "Mesa", glver.group(1) if glver else "")
        for iface in sorted(glob.glob("/sys/class/net/*/device")):
            n = iface.split("/")[4]
            drv = os.path.basename(os.path.realpath(iface + "/driver"))
            state = read(f"/sys/class/net/{n}/operstate", "")
            self.add("Red", f"Interfaz {n}", state, drv, self.modver(drv))

    def discos(self):
        for line in run(["lsblk", "-dno", "NAME,SIZE,ROTA,TRAN,MODEL"]).splitlines():
            parts = line.split(None, 4)
            if len(parts) < 4 or parts[0].startswith(("loop", "zram", "sr")):
                continue
            name, size, rota, tran = parts[:4]
            model = parts[4] if len(parts) > 4 else ""
            kind = "HDD" if rota == "1" else "SSD"
            self.add("Almacenamiento", model or name, f"/dev/{name} · {size} · {kind}",
                     tran if tran != "" else "", "")

    def usb(self):
        for line in run(["lsusb"]).splitlines():
            m = re.match(r"Bus (\d+) Device (\d+): ID (\w+:\w+) (.*)", line)
            if not m or "root hub" in m.group(4) or re.search(r"\bHub\b", m.group(4)):
                continue
            desc, vid = m.group(4), m.group(3)
            drivers = set()
            for d in glob.glob("/sys/bus/usb/devices/*"):
                if (read(d + "/idVendor", "") + ":" + read(d + "/idProduct", "")) == vid:
                    for intf in glob.glob(f"{d}:*/driver"):
                        drivers.add(os.path.basename(os.path.realpath(intf)))
            cat = "Bluetooth" if "Bluetooth" in desc else (
                "Entrada" if any(k in desc for k in ("Keyboard", "Trackpad", "Mouse", "IR Receiver")) else "USB")
            drv = ", ".join(sorted(drivers))
            first = sorted(drivers)[0] if drivers else ""
            self.add(cat, desc, f"ID {vid}", drv, self.modver(first) if first not in ("usb", "usbhid", "hub") else "")
        if glob.glob("/sys/class/bluetooth/hci*"):
            for h in glob.glob("/sys/class/bluetooth/hci*"):
                self.add("Bluetooth", os.path.basename(h), "adaptador activo", "btusb + btbcm",
                         self.modver("btusb"))
        for name in sorted(glob.glob("/sys/class/input/input*/name")):
            n = read(name, "")
            if n == "bcm5974":
                self.add("Entrada", "Trackpad multitouch", "bcm5974", "bcm5974", self.modver("bcm5974"))

    def audio(self):
        for codec in sorted(glob.glob("/proc/asound/card*/codec#*")):
            c = (read(codec, "") or "").splitlines()
            name = c[0].replace("Codec:", "").strip() if c else "?"
            mod = "snd_hda_codec_cirrus" if "Cirrus" in name else ""
            self.add("Audio", "Códec", name, mod or "snd_hda_codec", self.modver(mod) if mod else "")
        pw = run(["pactl", "info"])
        srv = re.search(r"Server Name: (.+)", pw)
        if srv:
            self.add("Audio", "Servidor de sonido", srv.group(1))

    def sensores(self):
        smc = "/sys/devices/platform/applesmc.768"
        if os.path.isdir(smc):
            fans = glob.glob(smc + "/fan*_input")
            temps = glob.glob(smc + "/temp*_input")
            self.add("Sensores y SMC", "Apple SMC", f"{len(fans)} ventilador(es) · {len(temps)} sensores",
                     "applesmc", self.modver("applesmc"))
            for f in sorted(fans):
                base = f[:-6]
                self.add("Sensores y SMC", f"Ventilador {(read(base + '_label', '') or '').strip()}",
                         f"{read(f)} rpm (rango {read(base + '_min')}–{read(base + '_max')})")
        svc = run(["systemctl", "is-active", "fancontrold"]).strip()
        self.add("Sensores y SMC", "Servicio fancontrold", svc, "", "")
        for hw in glob.glob("/sys/class/hwmon/hwmon*"):
            n = read(hw + "/name", "")
            if n == "coretemp":
                self.add("Sensores y SMC", "Temperatura CPU", "coretemp", "coretemp", self.modver("coretemp"))

    def bateria(self):
        for b in glob.glob("/sys/class/power_supply/BAT*"):
            full = int(read(b + "/energy_full", read(b + "/charge_full", "0")) or 0)
            design = int(read(b + "/energy_full_design", read(b + "/charge_full_design", "0")) or 0)
            health = f"{full * 100 / design:.0f} % de salud" if design else ""
            cycles = read(b + "/cycle_count", "")
            self.add("Batería", f"{read(b + '/manufacturer', '')} {read(b + '/model_name', '')}".strip(),
                     f"{health} · {cycles} ciclos · {read(b + '/technology', '')}", "sbs", self.modver("sbs"))

    def camara(self):
        vids = glob.glob("/sys/class/video4linux/video*")
        if vids:
            for v in vids:
                self.add("Cámara", read(v + "/name", "Cámara"), os.path.basename(v), "uvcvideo",
                         self.modver("uvcvideo"))
        else:
            self.add("Cámara", "FaceTime HD", "No detectada (puede estar desconectada o desactivada)")

    def modulos(self):
        for mod, desc in APPLE_MODULES.items():
            if mod in self.loaded:
                self.add("Módulos del kernel (Mac)", mod, desc, "cargado", self.modver(mod))


class SistemaPage(Page):
    title = "Sistema"
    icon = "computer"

    def __init__(self, win):
        super().__init__(win)
        model = read("/sys/class/dmi/id/product_name", "") or ""
        head = Gtk.Box(spacing=16, margin_top=8)
        img = Gtk.Image.new_from_pixbuf(win.icon_pixbuf(72)) if win.icon_pixbuf(72) else Gtk.Image()
        head.pack_start(img, False, False, 0)
        v = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, valign=Gtk.Align.CENTER)
        t = Gtk.Label(xalign=0)
        t.set_markup(f"<span size='x-large'><b>{GLib.markup_escape_text(MODELS.get(model, model))}</b></span>")
        v.pack_start(t, False, False, 0)
        s = Gtk.Label(label=f"{model} · Linux {platform.release()}", xalign=0)
        s.get_style_context().add_class("dim-label")
        v.pack_start(s, False, False, 0)
        head.pack_start(v, True, True, 0)
        self.put(head)

        self.section("Componentes, drivers y versiones")
        # col 4 = tooltip con el texto completo (las columnas se recortan con «…»)
        self.store = Gtk.TreeStore(str, str, str, str, str)
        self.tree = Gtk.TreeView(model=self.store, tooltip_column=4)
        for i, (title, width, expand) in enumerate((("Componente", 220, True), ("Detalle", 160, True),
                                                     ("Driver", 90, False), ("Versión", 120, False))):
            cell = Gtk.CellRendererText(ellipsize=Pango.EllipsizeMode.END)
            col = Gtk.TreeViewColumn(title, cell, markup=0) if i == 0 else \
                Gtk.TreeViewColumn(title, cell, text=i)
            col.set_resizable(True)
            col.set_expand(expand)
            col.set_min_width(width)
            col.set_sizing(Gtk.TreeViewColumnSizing.FIXED)
            col.set_fixed_width(width)
            self.tree.append_column(col)
        self.spinner = Gtk.Spinner(active=True)
        self.put(self.spinner)
        self.put(self.tree, expand=True)

        btns = Gtk.Box(spacing=8)
        for label, cb in (("Copiar informe", self.on_copy), ("Guardar informe…", self.on_save),
                          ("Actualizar", lambda _: self.load())):
            b = Gtk.Button(label=label)
            b.connect("clicked", cb)
            btns.pack_start(b, False, False, 0)
        self.put(btns)
        self.cats = {}
        self.load()

    def load(self):
        self.spinner.start()
        self.spinner.show()
        threading.Thread(target=lambda: GLib.idle_add(self.populate, Inventory().collect()),
                         daemon=True).start()

    def populate(self, cats):
        self.cats = cats
        self.store.clear()
        order = ["Equipo", "Procesador", "Memoria", "Gráficos", "Almacenamiento", "Red", "Bluetooth",
                 "Audio", "Entrada", "Cámara", "Batería", "Sensores y SMC", "USB", "USB y controladoras",
                 "Chipset", "Módulos del kernel (Mac)"]
        for cat in order + sorted(set(cats) - set(order)):
            if cat not in cats:
                continue
            parent = self.store.append(None, [f"<b>{GLib.markup_escape_text(cat)}</b>", "", "", "", None])
            for comp, detail, drv, ver in cats[cat]:
                esc = GLib.markup_escape_text
                rest = [x for x in (detail, drv and f"Driver: {drv}", ver and f"Versión: {ver}") if x]
                tip = f"<b>{esc(comp)}</b>" + "".join(f"\n{esc(x)}" for x in rest)
                self.store.append(parent, [esc(comp), detail, drv, ver, tip])
        self.tree.expand_all()
        self.spinner.stop()
        self.spinner.hide()
        return False

    def report(self):
        lines = ["Boot Camp para Linux — Informe del sistema", ""]
        for cat, rows in self.cats.items():
            lines.append(f"== {cat}")
            for comp, detail, drv, ver in rows:
                extra = " | ".join(x for x in (detail, drv and f"driver: {drv}", ver) if x)
                lines.append(f"  - {comp}: {extra}")
            lines.append("")
        return "\n".join(lines)

    def on_copy(self, _):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self.report(), -1)

    def on_save(self, _):
        d = Gtk.FileChooserDialog(title="Guardar informe", transient_for=self.win,
                                  action=Gtk.FileChooserAction.SAVE)
        d.add_buttons("Cancelar", Gtk.ResponseType.CANCEL, "Guardar", Gtk.ResponseType.OK)
        d.set_current_name("informe-mac.txt")
        d.set_do_overwrite_confirmation(True)
        if d.run() == Gtk.ResponseType.OK:
            with open(d.get_filename(), "w") as f:
                f.write(self.report())
        d.destroy()
