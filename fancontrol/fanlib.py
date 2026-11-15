"""Código compartido: sensores, ventilador, curva y configuración."""

import glob
import json
import os
import time

SMC = "/sys/devices/platform/applesmc.768"
CONFIG_PATH = "/etc/fancontrol/config.json"
STATUS_PATH = "/run/fancontrol/status.json"

DEFAULT_CONFIG = {
    "mode": "curve",            # auto | manual | curve
    "manual_pct": 50,
    # (temperatura CPU °C, % entre RPM mínima y máxima)
    "curve": [[40, 0], [50, 30], [57, 65], [63, 100]],
    "alert_temp": 70,           # aviso en el escritorio
    "emergency_temp": 75,       # fuerza el máximo en cualquier modo
}

SMC_LABELS = {
    "TA0P": "Ambiente",
    "TB0T": "Batería (carcasa)",
    "TB1T": "Batería 1",
    "TB2T": "Batería 2",
    "TC0E": "CPU (PECI)",
    "TC0F": "CPU (PECI filtrado)",
    "TC0P": "CPU proximidad",
    "TC1C": "CPU núcleo 1",
    "TC2C": "CPU núcleo 2",
    "TCGC": "GPU Intel (PECI)",
    "TCSA": "CPU System Agent",
    "TCXC": "CPU (PECI máx.)",
    "TG1D": "GPU NVIDIA (die)",
    "TM0P": "Memoria proximidad",
    "TM0S": "Memoria (slot)",
    "TPCD": "Chipset PCH",
    "Th1H": "Disipador",
    "Ts0P": "Reposamuñecas",
    "Ts0S": "Bahía memoria",
}


def read(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return None


def write(path, value):
    with open(path, "w") as f:
        f.write(str(value))


class Fan:
    def __init__(self, idx):
        self.idx = idx
        self.base = f"{SMC}/fan{idx}_"
        self.label = (read(self.base + "label") or f"Fan {idx}").strip()
        self.min = int(read(self.base + "min") or 2000)
        self.max = int(read(self.base + "max") or 6200)

    def rpm(self):
        v = read(self.base + "input")
        return int(v) if v else 0

    def pct_to_rpm(self, pct):
        return int(self.min + (self.max - self.min) * pct / 100)

    def set_auto(self):
        write(self.base + "manual", 0)

    def set_pct(self, pct):
        write(self.base + "manual", 1)
        write(self.base + "output", self.pct_to_rpm(max(0, min(100, pct))))


def find_fans():
    fans = []
    for p in sorted(glob.glob(f"{SMC}/fan*_input")):
        fans.append(Fan(int(os.path.basename(p)[3:].split("_")[0])))
    return fans


def read_temps():
    """Lista de (grupo, nombre, °C)."""
    temps = []
    for hw in glob.glob("/sys/class/hwmon/hwmon*"):
        if read(f"{hw}/name") != "coretemp":
            continue
        for inp in sorted(glob.glob(f"{hw}/temp*_input")):
            label = read(inp.replace("_input", "_label")) or "CPU"
            label = label.replace("Package id 0", "CPU paquete").replace("Core", "Núcleo")
            val = read(inp)
            if val:
                temps.append(("CPU (coretemp)", label, int(val) / 1000))
    smc = glob.glob(f"{SMC}/temp*_input")
    for inp in sorted(smc, key=lambda p: int(p.split("temp")[-1].split("_")[0])):
        key = (read(inp.replace("_input", "_label")) or "").strip()
        val = read(inp)
        if not val:
            continue
        c = int(val) / 1000
        if c < 5 or c > 130:  # sensores sin uso (TC0J, TCTD...)
            continue
        temps.append(("SMC", f"{SMC_LABELS.get(key, key)} ({key})", c))
    return temps


def cpu_temp(temps):
    cpu = [t for g, _, t in temps if g == "CPU (coretemp)"]
    return max(cpu) if cpu else max((t for _, _, t in temps), default=0)


def curve_percent(temp, curve):
    if temp <= curve[0][0]:
        return curve[0][1]
    for (t1, p1), (t2, p2) in zip(curve, curve[1:]):
        if temp <= t2:
            return p1 + (p2 - p1) * (temp - t1) / (t2 - t1)
    return curve[-1][1]


def _num(v, lo, hi, default):
    try:
        return max(lo, min(hi, float(v)))
    except (TypeError, ValueError):
        return default


def load_config():
    """Lee y valida la configuración (el archivo lo puede editar cualquier usuario del grupo sudo)."""
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH) as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return cfg
    if raw.get("mode") in ("auto", "manual", "curve"):
        cfg["mode"] = raw["mode"]
    cfg["manual_pct"] = _num(raw.get("manual_pct"), 0, 100, cfg["manual_pct"])
    cfg["alert_temp"] = _num(raw.get("alert_temp"), 40, 100, cfg["alert_temp"])
    cfg["emergency_temp"] = _num(raw.get("emergency_temp"), 50, 100, cfg["emergency_temp"])
    try:
        curve = sorted([_num(t, 0, 110, 0), _num(p, 0, 100, 0)] for t, p in raw["curve"])
        if len(curve) >= 2 and len({t for t, _ in curve}) == len(curve):
            cfg["curve"] = curve
    except (KeyError, TypeError, ValueError):
        pass
    return cfg


def save_config(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, CONFIG_PATH)


def read_status():
    """Estado publicado por el servicio, o None si no está corriendo."""
    try:
        with open(STATUS_PATH) as f:
            st = json.load(f)
        if time.time() - st.get("time", 0) < 10:
            return st
    except (OSError, ValueError):
        pass
    return None
