#!/usr/bin/python3
"""
Helper con privilegios de Boot Camp. Se ejecuta SOLO vía pkexec desde la interfaz.
Acepta un conjunto cerrado de acciones y valida cada argumento.

  hid_apple  fnmode=0..3 swap_opt_cmd=0|1 swap_fn_leftctrl=0|1 swap_ctrl_cmd=0|1
  logind     HandleLidSwitch=<acción> HandleLidSwitchExternalPower=<acción> ...
  service    fancontrold start|stop|restart|enable|disable
"""
import os
import subprocess
import sys

HID_PARAMS = {"fnmode": {"0", "1", "2", "3"}, "swap_opt_cmd": {"0", "1"},
              "swap_fn_leftctrl": {"0", "1"}, "swap_ctrl_cmd": {"0", "1"}}
HID_CONF = "/etc/modprobe.d/bootcamp-hid_apple.conf"

LOGIND_KEYS = {"HandleLidSwitch", "HandleLidSwitchExternalPower", "HandleLidSwitchDocked",
               "HandlePowerKey"}
LOGIND_VALUES = {"ignore", "poweroff", "reboot", "halt", "suspend", "hibernate",
                 "hybrid-sleep", "suspend-then-hibernate", "lock"}
LOGIND_CONF = "/etc/systemd/logind.conf.d/bootcamp.conf"

SERVICES = {"fancontrold"}
SERVICE_OPS = {"start", "stop", "restart", "enable", "disable"}


def die(msg):
    print(msg)
    sys.exit(2)


def parse_pairs(args, allowed_keys, allowed_values):
    pairs = {}
    for a in args:
        if "=" not in a:
            die(f"Argumento inválido: {a}")
        k, v = a.split("=", 1)
        if k not in allowed_keys:
            die(f"Clave no permitida: {k}")
        vals = allowed_values[k] if isinstance(allowed_values, dict) else allowed_values
        if v not in vals:
            die(f"Valor no permitido para {k}: {v}")
        pairs[k] = v
    if not pairs:
        die("Sin parámetros")
    return pairs


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        f.write(content)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def hid_apple(args):
    pairs = parse_pairs(args, HID_PARAMS.keys(), HID_PARAMS)
    # 1) Aplicar en caliente
    for k, v in pairs.items():
        p = f"/sys/module/hid_apple/parameters/{k}"
        if os.path.exists(p):
            with open(p, "w") as f:
                f.write(v)
    # 2) Persistir (fusiona con lo que ya hubiera en el archivo)
    current = {}
    try:
        for line in open(HID_CONF):
            if line.startswith("options hid_apple"):
                for tok in line.split()[2:]:
                    if "=" in tok:
                        k, v = tok.split("=", 1)
                        if k in HID_PARAMS:
                            current[k] = v
    except OSError:
        pass
    current.update(pairs)
    opts = " ".join(f"{k}={v}" for k, v in sorted(current.items()))
    write_file(HID_CONF, f"# Generado por Boot Camp para Linux\noptions hid_apple {opts}\n")
    # 3) hid_apple se carga desde el initramfs: regenerarlo para que valga al arrancar
    subprocess.run(["update-initramfs", "-u"], check=False,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"hid_apple: {opts}")


def logind(args):
    pairs = parse_pairs(args, LOGIND_KEYS, LOGIND_VALUES)
    current = {}
    try:
        for line in open(LOGIND_CONF):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                if k in LOGIND_KEYS and v in LOGIND_VALUES:
                    current[k] = v
    except OSError:
        pass
    current.update(pairs)
    body = "".join(f"{k}={v}\n" for k, v in sorted(current.items()))
    write_file(LOGIND_CONF, f"# Generado por Boot Camp para Linux\n[Login]\n{body}")
    # logind relee la configuración con SIGHUP sin cerrar la sesión
    subprocess.run(["systemctl", "kill", "-s", "HUP", "systemd-logind"], check=False)
    print("logind actualizado")


def service(args):
    if len(args) != 2 or args[0] not in SERVICES or args[1] not in SERVICE_OPS:
        die("Uso: service fancontrold start|stop|restart|enable|disable")
    r = subprocess.run(["systemctl", args[1], args[0]], capture_output=True, text=True)
    print((r.stdout + r.stderr).strip())
    sys.exit(r.returncode)


def main():
    if os.geteuid() != 0:
        die("Este helper debe ejecutarse con pkexec")
    if len(sys.argv) < 2:
        die(__doc__)
    action, args = sys.argv[1], sys.argv[2:]
    {"hid_apple": hid_apple, "logind": logind, "service": service}.get(
        action, lambda _: die(f"Acción desconocida: {action}"))(args)


if __name__ == "__main__":
    main()
