#!/usr/bin/env python3
"""Servicio (root) que controla el ventilador según /etc/fancontrol/config.json."""

import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fanlib import (STATUS_PATH, cpu_temp, curve_percent, find_fans,  # noqa: E402
                    load_config, read_temps)

INTERVAL = 2.0
MAX_DROP_PER_TICK = 4.0  # % por ciclo: sube enseguida, baja de a poco (evita que oscile)

running = True


def stop(*_):
    global running
    running = False


def publish(status):
    os.makedirs(os.path.dirname(STATUS_PATH), exist_ok=True)
    tmp = STATUS_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(status, f)
    os.chmod(tmp, 0o644)
    os.replace(tmp, STATUS_PATH)


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    fans = find_fans()
    if not fans:
        print("No se encontró ningún ventilador applesmc", file=sys.stderr)
        sys.exit(1)

    current = None  # % aplicado actualmente (None = automático SMC)
    print(f"fancontrold iniciado: {[f.label for f in fans]}", flush=True)

    while running:
        cfg = load_config()
        temps = read_temps()
        cpu = cpu_temp(temps)
        mode = cfg["mode"]
        emergency = cpu >= cfg["emergency_temp"]

        if emergency:
            target = 100.0
        elif mode == "manual":
            target = cfg["manual_pct"]
        elif mode == "curve":
            target = curve_percent(cpu, cfg["curve"])
        else:
            target = None

        try:
            if target is None:
                if current is not None:
                    for f in fans:
                        f.set_auto()
                current = None
            else:
                if current is not None and mode == "curve" and not emergency:
                    target = max(target, current - MAX_DROP_PER_TICK)
                for f in fans:
                    f.set_pct(target)
                current = target
        except OSError as e:
            print(f"Error escribiendo en el SMC: {e}", file=sys.stderr, flush=True)

        publish({
            "time": time.time(),
            "mode": mode,
            "cpu": cpu,
            "target_pct": current,
            "emergency": emergency,
        })
        time.sleep(INTERVAL)

    # Al detener el servicio, devolver el control al SMC
    for f in fans:
        try:
            f.set_auto()
        except OSError:
            pass
    try:
        os.remove(STATUS_PATH)
    except OSError:
        pass
    print("fancontrold detenido", flush=True)


if __name__ == "__main__":
    main()
