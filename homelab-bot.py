#!/usr/bin/env python3
import json
import socket
import os
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
ALLOWED_CHAT_ID = int(os.environ["TELEGRAM_CHAT_ID"])
API = f"https://api.telegram.org/bot{BOT_TOKEN}"


# ── Telegram API ──────────────────────────────────────────────────────────────

def tg(method, **params):
    data = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(f"{API}/{method}", data=data)
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)

def get_updates(offset):
    return tg("getUpdates", offset=offset, timeout=30, allowed_updates="message")

def send(chat_id, text):
    tg("sendMessage", chat_id=chat_id, text=text, parse_mode="HTML")


# ── System metrics ────────────────────────────────────────────────────────────

def uptime():
    secs = float(Path("/proc/uptime").read_text().split()[0])
    d = int(secs // 86400)
    h = int((secs % 86400) // 3600)
    m = int((secs % 3600) // 60)
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts)

def cpu_temp():
    for name_file in Path("/sys/class/hwmon").glob("*/name"):
        if name_file.read_text().strip() == "coretemp":
            t = name_file.parent / "temp1_input"
            if t.exists():
                return int(t.read_text()) // 1000
    return None

def ram():
    info = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        k, v = line.split(":", 1)
        info[k.strip()] = int(v.split()[0])
    total = info["MemTotal"]
    avail = info["MemAvailable"]
    used  = total - avail
    pct   = used * 100 // total
    def h(kb):
        return f"{kb/1048576:.1f}G" if kb > 1048576 else f"{kb/1024:.0f}M"
    return h(used), h(avail), pct

def disk():
    st    = os.statvfs("/")
    total = st.f_blocks * st.f_frsize
    free  = st.f_bavail * st.f_frsize
    pct   = (total - free) * 100 // total
    def h(b):
        return f"{b/1e9:.0f}G" if b > 1e9 else f"{b/1e6:.0f}M"
    return h(free), h(total), pct

def battery():
    cap_p = Path("/sys/class/power_supply/BAT0/capacity")
    ac_p  = Path("/sys/class/power_supply/AC/online")
    en_p  = Path("/sys/class/power_supply/BAT0/power_now")

    if not cap_p.exists():
        return None, None, None

    cap = int(cap_p.read_text())
    ac = int(ac_p.read_text()) if ac_p.exists() else None
    power_now = int(en_p.read_text()) if en_p.exists() else None

    return cap, ac, power_now

def battery_info():
    """Devuelve estado de batería con estimado de tiempo restante."""
    cap, ac, power_now = battery()

    if cap is None:
        return None

    info = {"capacity": cap, "ac": ac}

    # Estimar tiempo restante si está en batería
    if ac is not None and ac != 1 and power_now and power_now > 0:
        power_w = power_now / 1e6
        hours_left = (cap / 100.0) * 3600 / power_w
        info["hours_left"] = max(0, hours_left)

    return info

def battery_msg():
    """Mensaje formateado de estado de batería."""
    info = battery_info()

    if info is None:
        return "❌ Sin información de batería"

    cap = info["capacity"]
    ac = info["ac"]

    lines = ["<b>🔋 Batería</b>", ""]

    if ac == 1:
        lines.append(f"⚡ Cargando: {cap}%")
    else:
        if cap < 20:
            icon = "🔴"
        elif cap < 50:
            icon = "🟡"
        else:
            icon = "🟢"
        lines.append(f"{icon} En batería: {cap}%")

        if "hours_left" in info:
            h = int(info["hours_left"])
            m = int((info["hours_left"] - h) * 60)
            if h > 0 or m > 0:
                lines.append(f"⏱ Tiempo restante: {h}h {m}m")

    register_temperature()
    return "\n".join(lines)

def load_avg():
    parts = Path("/proc/loadavg").read_text().split()
    return parts[0], parts[1], parts[2]

def register_temperature():
    """Guarda temperatura actual en temperature.json si existe sensor. Fallos silenciosos en persistencia."""
    temp = cpu_temp()
    if temp is None:
        return

    data_file = Path("/tmp/temperature.json")
    try:
        if data_file.exists():
            data = json.loads(data_file.read_text())
        else:
            data = []

        # Limpiar datos > 24h
        now = int(time.time())
        data = [d for d in data if now - d.get("timestamp", 0) < 86400]

        # Agregar nuevo dato
        data.append({"timestamp": now, "temp": temp})

        # Guardar
        data_file.write_text(json.dumps(data))
    except (IOError, json.JSONDecodeError):
        pass  # Fallos silenciosos en persistencia

def docker_info():
    out = subprocess.check_output(
        ["docker", "ps", "-a", "--format", "{{.Names}}\t{{.Status}}"],
        text=True, timeout=5,
    )
    return [(l.split("\t")[0], l.split("\t")[1]) for l in out.strip().splitlines() if l]


# ── Message builders ──────────────────────────────────────────────────────────

def ci(val, warn, crit):
    return "🔴" if val >= crit else "🟡" if val >= warn else "🟢"

def status_msg():
    lines = [f"<b>📊 {socket.gethostname()}</b>", ""]

    lines.append(f"⏱ <b>Uptime</b>   {uptime()}")

    temp = cpu_temp()
    if temp is not None:
        lines.append(f"{ci(temp,60,80)} <b>CPU</b>      {temp}°C")

    used, free, pct = ram()
    lines.append(f"{ci(pct,70,90)} <b>RAM</b>      {used} usada · {free} libre ({pct}%)")

    dfree, dtotal, dpct = disk()
    lines.append(f"{ci(dpct,70,85)} <b>Disco</b>    {dfree} libre de {dtotal} ({dpct}%)")

    cap, ac, _ = battery()
    if cap is not None:
        if ac == 1:
            lines.append(f"⚡ <b>Batería</b>  {cap}% · cargando")
        else:
            icon = "🔴" if cap < 20 else "🟡" if cap < 50 else "🟢"
            lines.append(f"{icon} <b>Batería</b>  {cap}% · en batería")

    l1, l5, l15 = load_avg()
    lines.append(f"📈 <b>Load</b>     {l1}  {l5}  {l15}")

    try:
        containers  = docker_info()
        running     = sum(1 for _, s in containers if s.startswith("Up"))
        unhealthy   = sum(1 for _, s in containers if "unhealthy" in s)
        total       = len(containers)
        icon = "🔴" if running < total else "🟡" if unhealthy else "🟢"
        suffix = f" · {unhealthy} unhealthy" if unhealthy else ""
        lines.append(f"{icon} <b>Docker</b>   {running}/{total} corriendo{suffix}")
    except Exception:
        lines.append("❓ <b>Docker</b>   no disponible")

    return "\n".join(lines)

def docker_msg():
    try:
        containers = docker_info()
    except Exception as e:
        return f"❌ Error consultando Docker: {e}"
    lines = ["<b>🐳 Contenedores</b>", ""]
    for name, status in sorted(containers):
        if "unhealthy" in status:
            icon = "🟡"
        elif status.startswith("Up"):
            icon = "🟢"
        else:
            icon = "🔴"
        lines.append(f"{icon} <code>{name}</code>\n   {status}")
    return "\n".join(lines)

def help_msg():
    return (
        "Comandos disponibles:\n\n"
        "/status — estado del sistema\n"
        "/docker — detalle de contenedores\n"
        "/help   — este mensaje"
    )


# ── Dispatcher ────────────────────────────────────────────────────────────────

def handle(message):
    if message.get("chat", {}).get("id") != ALLOWED_CHAT_ID:
        return
    cmd = message.get("text", "").strip().split()[0].lower() if message.get("text") else ""
    if cmd == "/docker":
        send(ALLOWED_CHAT_ID, docker_msg())
    elif cmd == "/help":
        send(ALLOWED_CHAT_ID, help_msg())
    else:
        send(ALLOWED_CHAT_ID, status_msg())


# ── Main loop ─────────────────────────────────────────────────────────────────

def main():
    offset  = 0
    backoff = 5
    while True:
        try:
            result  = get_updates(offset)
            backoff = 5
            for upd in result.get("result", []):
                offset = upd["update_id"] + 1
                if "message" in upd:
                    handle(upd["message"])
        except urllib.error.URLError:
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)
        except Exception:
            time.sleep(backoff)
            backoff = min(backoff * 2, 60)

if __name__ == "__main__":
    main()
