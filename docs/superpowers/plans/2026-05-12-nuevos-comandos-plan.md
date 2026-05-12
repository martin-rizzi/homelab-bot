# Nuevos comandos para homelab-bot — Plan de Implementación

> **Para workers agenticos:** Usa superpowers:subagent-driven-development (recomendado) o superpowers:executing-plans para ejecutar este plan tarea por tarea. Los pasos usan sintaxis checkbox (`- [ ]`) para tracking.

**Objetivo:** Agregar 4 nuevos comandos al bot: `/bateria`, `/procesos`, `/internet`, `/temperatura` con persistencia de datos históricos.

**Arquitectura:** Todas las funciones nuevas se agregan a `homelab-bot.py`. Se crea un archivo `temperature.json` para histórico de temperaruras que se limpia automáticamente. Cada comando es independiente y puede fallar sin afectar otros.

**Stack:** Python 3 stdlib + `speedtest-cli` (ya instalado)

---

## Tareas

### Task 1: Agregar función `register_temperature()`

Función base para persistencia de temperatura. Se llama desde todos los comandos.

**Archivos:**
- Modificar: `homelab-bot.py` (después de `load_avg()`, antes de `docker_info()`)

- [ ] **Step 1: Escribir la función `register_temperature()`**

Insertar después de `load_avg()` en `homelab-bot.py`:

```python
def register_temperature():
    """Guarda temperatura actual en temperature.json si existe sensor."""
    temp = cpu_temp()
    if temp is None:
        return
    
    data_file = Path("/usr/local/bin/temperature.json")
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
    except Exception:
        pass  # Fallos silenciosos en persistencia
```

- [ ] **Step 2: Probar que la función se puede llamar**

En una terminal, correr:
```bash
cd /home/martin/Documents/homelab-bot
python3 -c "
import homelab_bot
# Debería ejecutarse sin errores
print('OK')
"
```

Expected: `OK` impreso, sin errores

- [ ] **Step 3: Commit**

```bash
git add homelab-bot.py
git commit -m "feat: add register_temperature() function for data persistence"
```

---

### Task 2: Agregar función `battery_info()`

Obtiene estado de batería y estima tiempo restante si está disponible.

**Archivos:**
- Modificar: `homelab-bot.py` (reemplazar función `battery()` existente con versión mejorada + nueva función `battery_info()`)

- [ ] **Step 1: Reemplazar `battery()` con versión que devuelve más datos**

Reemplazar la función `battery()` existente (líneas 75-80) con:

```python
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
```

- [ ] **Step 2: Agregar función `battery_info()`**

Insertar después de `battery()`:

```python
def battery_info():
    """Devuelve estado de batería con estimado de tiempo restante."""
    cap, ac, power_now = battery()
    
    if cap is None:
        return None
    
    info = {"capacity": cap, "ac": ac}
    
    # Estimar tiempo restante si está en batería
    if ac != 1 and power_now and power_now > 0:
        # power_now está en microwatios, convertir a ratio por hora
        hours_left = (cap / 100.0) * (3600 / (power_now / 1e6)) if cap > 0 else 0
        info["hours_left"] = max(0, hours_left)
    
    return info
```

- [ ] **Step 3: Agregar función `battery_msg()`**

Insertar después de `battery_info()`:

```python
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
```

- [ ] **Step 4: Actualizar `status_msg()` para usar la versión mejorada**

En `status_msg()`, reemplazar las líneas de batería (114-120) con:

```python
    cap, ac, _ = battery()
    if cap is not None:
        if ac == 1:
            lines.append(f"⚡ <b>Batería</b>  {cap}% · cargando")
        else:
            icon = "🔴" if cap < 20 else "🟡" if cap < 50 else "🟢"
            lines.append(f"{icon} <b>Batería</b>  {cap}% · en batería")
```

- [ ] **Step 5: Probar que compila**

```bash
python3 -c "import homelab_bot; homelab_bot.battery_info()"
```

Expected: Sin errores (puede devolver None si no hay batería)

- [ ] **Step 6: Commit**

```bash
git add homelab-bot.py
git commit -m "feat: add battery_info() and battery_msg() for /bateria command"
```

---

### Task 3: Agregar función `top_processes()`

Obtiene los 5 procesos con mayor consumo combinado (CPU + RAM).

**Archivos:**
- Modificar: `homelab-bot.py` (insertar después de `docker_info()`)

- [ ] **Step 1: Agregar función auxiliar `get_cpu_percent()`**

Insertar después de `docker_info()`:

```python
def get_cpu_percent(pid_stat_line):
    """Calcula CPU% de una línea de /proc/[pid]/stat."""
    try:
        fields = pid_stat_line.split()
        if len(fields) < 15:
            return 0
        
        utime = int(fields[13])
        stime = int(fields[14])
        total_time = utime + stime
        
        # CPU% muy simplificado (sin escalar por núcleos)
        # Devuelve 0-100 como aproximación
        return min(100, total_time // 100000)
    except (ValueError, IndexError):
        return 0
```

- [ ] **Step 2: Agregar función `top_processes()`**

Insertar después de `get_cpu_percent()`:

```python
def top_processes():
    """Devuelve top 5 procesos por consumo combinado (CPU + RAM)."""
    processes = []
    
    for pid_dir in Path("/proc").iterdir():
        if not pid_dir.is_dir():
            continue
        
        try:
            pid = int(pid_dir.name)
            if pid == os.getpid():
                continue
            
            # Leer nombre del proceso
            comm_file = pid_dir / "comm"
            if not comm_file.exists():
                continue
            name = comm_file.read_text().strip()
            
            # Leer CPU
            stat_file = pid_dir / "stat"
            if not stat_file.exists():
                continue
            cpu_pct = get_cpu_percent(stat_file.read_text())
            
            # Leer RAM
            status_file = pid_dir / "status"
            if not status_file.exists():
                continue
            rss_mb = 0
            for line in status_file.read_text().splitlines():
                if line.startswith("VmRSS:"):
                    rss_kb = int(line.split()[1])
                    rss_mb = rss_kb // 1024
                    break
            
            # Score combinado
            score = cpu_pct + (rss_mb // 100)
            processes.append((name, cpu_pct, rss_mb, score))
        
        except (ValueError, FileNotFoundError, PermissionError):
            continue
    
    # Top 5 por score
    return sorted(processes, key=lambda x: x[3], reverse=True)[:5]
```

- [ ] **Step 3: Agregar función `processes_msg()`**

Insertar después de `top_processes()`:

```python
def processes_msg():
    """Mensaje formateado de top 5 procesos."""
    try:
        procs = top_processes()
    except Exception as e:
        return f"❌ Error leyendo procesos: {e}"
    
    if not procs:
        return "❌ Sin procesos"
    
    lines = ["<b>🔝 Top 5 procesos</b>", ""]
    
    for i, (name, cpu, ram, _) in enumerate(procs, 1):
        lines.append(f"{i}. <code>{name}</code>")
        lines.append(f"   CPU: {cpu}% | RAM: {ram}MB")
        lines.append("")
    
    register_temperature()
    return "\n".join(lines)
```

- [ ] **Step 4: Probar que compila**

```bash
python3 -c "import homelab_bot; procs = homelab_bot.top_processes(); print(f'Found {len(procs)} processes')"
```

Expected: `Found N processes` (N >= 0)

- [ ] **Step 5: Commit**

```bash
git add homelab-bot.py
git commit -m "feat: add top_processes() and processes_msg() for /procesos command"
```

---

### Task 4: Agregar función `internet_speed()`

Mide velocidad usando speedtest-cli y ping a 8.8.8.8.

**Archivos:**
- Modificar: `homelab-bot.py` (insertar después de `processes_msg()`)

- [ ] **Step 1: Agregar función auxiliar `get_ping()`**

Insertar después de `processes_msg()`:

```python
def get_ping(host="8.8.8.8"):
    """Mide ping en ms a un host."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", host],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "time=" in line:
                    parts = line.split("time=")
                    if len(parts) > 1:
                        time_str = parts[1].split()[0]
                        return float(time_str)
        return None
    except Exception:
        return None
```

- [ ] **Step 2: Agregar función `internet_speed()`**

Insertar después de `get_ping()`:

```python
def internet_speed():
    """Mide velocidad con speedtest-cli."""
    try:
        import speedtest
        
        st = speedtest.Speedtest()
        st.get_best_server()
        
        download = st.download() / 1_000_000  # bps a Mbps
        upload = st.upload() / 1_000_000      # bps a Mbps
        ping = st.results.ping
        
        return {
            "download": download,
            "upload": upload,
            "ping": ping,
            "error": None
        }
    except Exception as e:
        return {"error": str(e)}
```

- [ ] **Step 3: Agregar función `internet_msg()`**

Insertar después de `internet_speed()`:

```python
def internet_msg():
    """Mensaje formateado de velocidad de conexión."""
    result = internet_speed()
    
    if result.get("error"):
        return f"⚠️ No se pudo medir velocidad: {result['error']}"
    
    lines = ["<b>🌐 Velocidad</b>", ""]
    lines.append(f"📥 Download: {result['download']:.1f} Mbps")
    lines.append(f"📤 Upload: {result['upload']:.1f} Mbps")
    lines.append(f"📡 Ping: {result['ping']:.0f} ms (8.8.8.8)")
    
    register_temperature()
    return "\n".join(lines)
```

- [ ] **Step 4: Probar que speedtest está importable**

```bash
python3 -c "import speedtest; print('speedtest-cli OK')"
```

Expected: `speedtest-cli OK`

- [ ] **Step 5: Commit**

```bash
git add homelab-bot.py
git commit -m "feat: add internet_speed() and internet_msg() for /internet command"
```

---

### Task 5: Agregar función `temperature_stats()`

Lee histórico de temperatura y calcula estadísticas de últimas 24h.

**Archivos:**
- Modificar: `homelab-bot.py` (insertar después de `internet_msg()`)

- [ ] **Step 1: Agregar función `temperature_stats()`**

Insertar después de `internet_msg()`:

```python
def temperature_stats():
    """Obtiene estadísticas de temperatura de últimas 24h."""
    data_file = Path("/usr/local/bin/temperature.json")
    
    if not data_file.exists():
        return None
    
    try:
        data = json.loads(data_file.read_text())
    except (json.JSONDecodeError, FileNotFoundError):
        return None
    
    if not data:
        return None
    
    # Filtrar últimas 24h
    now = int(time.time())
    recent = [d for d in data if now - d.get("timestamp", 0) < 86400]
    
    if len(recent) < 2:
        return None
    
    temps = [d["temp"] for d in recent]
    
    return {
        "max": max(temps),
        "min": min(temps),
        "avg": sum(temps) / len(temps),
        "current": temps[-1],
        "count": len(temps)
    }
```

- [ ] **Step 2: Agregar función `temperature_msg()`**

Insertar después de `temperature_stats()`:

```python
def temperature_msg():
    """Mensaje formateado de estadísticas de temperatura."""
    stats = temperature_stats()
    
    if stats is None:
        return "⏳ Sin datos de temperatura (necesita 24h)"
    
    lines = ["<b>🌡️ Temperatura (últimas 24h)</b>", ""]
    lines.append(f"📈 Máximo: {stats['max']}°C")
    lines.append(f"📉 Mínimo: {stats['min']}°C")
    lines.append(f"📊 Promedio: {stats['avg']:.1f}°C")
    lines.append(f"🔴 Actual: {stats['current']}°C")
    lines.append("")
    lines.append(f"📋 Registros: {stats['count']} muestras")
    
    register_temperature()
    return "\n".join(lines)
```

- [ ] **Step 3: Probar que compila**

```bash
python3 -c "import homelab_bot; stats = homelab_bot.temperature_stats(); print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add homelab-bot.py
git commit -m "feat: add temperature_stats() and temperature_msg() for /temperatura command"
```

---

### Task 6: Actualizar `status_msg()` para registrar temperatura

Cada vez que se consulta `/status`, se guarda la temperatura en el histórico.

**Archivos:**
- Modificar: `homelab-bot.py` (función `status_msg()`)

- [ ] **Step 1: Agregar llamada a `register_temperature()` al final de `status_msg()`**

En la función `status_msg()`, al final (línea 136), reemplazar:

```python
    return "\n".join(lines)
```

con:

```python
    register_temperature()
    return "\n".join(lines)
```

- [ ] **Step 2: Probar que compila**

```bash
python3 -c "import homelab_bot; msg = homelab_bot.status_msg(); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add homelab-bot.py
git commit -m "feat: register temperature in status_msg()"
```

---

### Task 7: Actualizar `handle()` para soportar los 4 nuevos comandos

Agregar casos para `/bateria`, `/procesos`, `/internet`, `/temperatura`.

**Archivos:**
- Modificar: `homelab-bot.py` (función `handle()`)

- [ ] **Step 1: Actualizar `handle()` con los 4 nuevos comandos**

Reemplazar el código de `handle()` (líneas 165-174) con:

```python
def handle(message):
    if message.get("chat", {}).get("id") != ALLOWED_CHAT_ID:
        return
    cmd = message.get("text", "").strip().split()[0].lower() if message.get("text") else ""
    
    if cmd == "/bateria":
        send(ALLOWED_CHAT_ID, battery_msg())
    elif cmd == "/procesos":
        send(ALLOWED_CHAT_ID, processes_msg())
    elif cmd == "/internet":
        send(ALLOWED_CHAT_ID, internet_msg())
    elif cmd == "/temperatura":
        send(ALLOWED_CHAT_ID, temperature_msg())
    elif cmd == "/docker":
        send(ALLOWED_CHAT_ID, docker_msg())
    elif cmd == "/help":
        send(ALLOWED_CHAT_ID, help_msg())
    else:
        send(ALLOWED_CHAT_ID, status_msg())
```

- [ ] **Step 2: Probar que compila**

```bash
python3 -c "import homelab_bot; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add homelab-bot.py
git commit -m "feat: add handlers for /bateria, /procesos, /internet, /temperatura commands"
```

---

### Task 8: Actualizar `help_msg()` con nuevos comandos

Agregar los 4 nuevos comandos a la lista de ayuda.

**Archivos:**
- Modificar: `homelab-bot.py` (función `help_msg()`)

- [ ] **Step 1: Reemplazar `help_msg()`**

Reemplazar la función `help_msg()` (líneas 154-160) con:

```python
def help_msg():
    return (
        "Comandos disponibles:\n\n"
        "/status       — estado del sistema\n"
        "/docker       — detalle de contenedores\n"
        "/bateria      — estado de batería y tiempo restante\n"
        "/procesos     — top 5 procesos por consumo\n"
        "/internet     — velocidad de conexión (speedtest)\n"
        "/temperatura  — estadísticas últimas 24h\n"
        "/help         — este mensaje"
    )
```

- [ ] **Step 2: Probar que compila**

```bash
python3 -c "import homelab_bot; msg = homelab_bot.help_msg(); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add homelab_bot.py
git commit -m "docs: update help message with new commands"
```

---

### Task 9: Verificación final e integración

Pruebas manuales de todos los comandos para garantizar que funcionan.

**Archivos:**
- No se modifican archivos (solo pruebas)

- [ ] **Step 1: Verificar que el script compila sin errores**

```bash
python3 homelab-bot.py &
sleep 2
kill %1
```

Expected: Se inicia sin errores, se detiene sin errores

- [ ] **Step 2: Verificar imports**

```bash
python3 -c "
import homelab_bot
assert hasattr(homelab_bot, 'battery_msg')
assert hasattr(homelab_bot, 'processes_msg')
assert hasattr(homelab_bot, 'internet_msg')
assert hasattr(homelab_bot, 'temperature_msg')
assert hasattr(homelab_bot, 'register_temperature')
print('✓ Todas las funciones existen')
"
```

Expected: `✓ Todas las funciones existen`

- [ ] **Step 3: Verificar que `/status` registra temperatura**

```bash
python3 -c "
import homelab_bot
msg = homelab_bot.status_msg()
print('✓ status_msg() devuelve:', msg[:50])
"
```

Expected: Mensaje de estado válido

- [ ] **Step 4: Verificar que `/temperatura` funciona sin datos**

```bash
python3 -c "
import homelab_bot
msg = homelab_bot.temperature_msg()
print('✓ temperature_msg():', msg[:50])
"
```

Expected: Mensaje sin datos o con datos si existen

- [ ] **Step 5: Verificar que `/bateria` funciona**

```bash
python3 -c "
import homelab_bot
msg = homelab_bot.battery_msg()
print('✓ battery_msg():', msg[:50])
"
```

Expected: Mensaje de batería (puede ser error si no hay batería)

- [ ] **Step 6: Verificar que `/procesos` funciona**

```bash
python3 -c "
import homelab_bot
msg = homelab_bot.processes_msg()
print('✓ processes_msg():', msg[:50])
"
```

Expected: Mensaje con procesos

- [ ] **Step 7: Verificar que `/help` actualizado**

```bash
python3 -c "
import homelab_bot
msg = homelab_bot.help_msg()
assert '/bateria' in msg
assert '/procesos' in msg
assert '/internet' in msg
assert '/temperatura' in msg
print('✓ help_msg() contiene nuevos comandos')
"
```

Expected: `✓ help_msg() contiene nuevos comandos`

- [ ] **Step 8: Commit final**

```bash
git add -A
git commit -m "test: verify all new commands compile and execute"
```

---

## Self-Review del Plan

✅ **Spec Coverage:**
- `/bateria` — Task 2 (battery_info, battery_msg)
- `/procesos` — Task 3 (top_processes, processes_msg)
- `/internet` — Task 4 (internet_speed, internet_msg)
- `/temperatura` — Task 5 (temperature_stats, temperature_msg)
- Persistencia temperatura — Task 1 (register_temperature)
- Limpieza de datos — Task 1 (cleanup en register_temperature)
- Actualizar help — Task 8
- Integración en handle() — Task 7
- Registro en status_msg() — Task 6

✅ **Placeholders:** Ninguno. Cada paso tiene código completo.

✅ **Consistencia de tipos:** 
- `battery()` devuelve `(cap, ac, power_now)` → Task 2 ✓
- `battery_info()` devuelve dict con keys específicas → Task 2 ✓
- `top_processes()` devuelve list de tuples → Task 3 ✓
- `temperature_stats()` devuelve dict o None → Task 5 ✓

✅ **Orden de tareas:** Correcto (base → funciones → integración → verificación)

---

## Ejecución

Plan guardado en `docs/superpowers/plans/2026-05-12-nuevos-comandos-plan.md`.

¿Cuál es tu preferencia para ejecutar?

**Opción A: Subagent-Driven (recomendado)**
- Dispatcher automático por tarea, review entre tareas
- Más rápido para tareas parallelizables
- Requiere superpowers:subagent-driven-development

**Opción B: Inline Execution**
- Ejecuto las tareas en esta sesión
- Control total, feedback inmediato
- Requiere superpowers:executing-plans
