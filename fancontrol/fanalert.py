#!/usr/bin/env python3
"""Corre en tu sesión de escritorio y avisa cuando la CPU pasa la temperatura de alerta."""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fanlib import cpu_temp, load_config, read_temps  # noqa: E402

INTERVAL = 3
REPEAT_EVERY = 60   # segundos entre avisos mientras siga caliente
HYSTERESIS = 3      # tiene que bajar 3°C bajo el umbral para "rearmarse"
SOUND = "/usr/share/sounds/freedesktop/stereo/dialog-warning.oga"


def notify(temp, limit):
    subprocess.run(["notify-send", "-u", "critical", "-i", "dialog-warning",
                    "-a", "Boot Camp", f"🌡 CPU a {temp:.0f} °C",
                    f"Superó el límite de alerta ({limit:.0f} °C). "
                    "El ventilador está al máximo; revisá qué programa está exigiendo la CPU."],
                   check=False)
    if os.path.exists(SOUND):
        subprocess.Popen(["paplay", SOUND], stderr=subprocess.DEVNULL)


def main():
    last_alert = 0
    alerting = False
    while True:
        limit = load_config()["alert_temp"]
        t = cpu_temp(read_temps())
        now = time.time()
        if t >= limit:
            if not alerting or now - last_alert >= REPEAT_EVERY:
                notify(t, limit)
                last_alert = now
            alerting = True
        elif t < limit - HYSTERESIS:
            alerting = False
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
