# Diseño: Nuevos comandos para homelab-bot

**Fecha:** 2026-05-12  
**Autor:** Martin Rizzi  
**Alcance:** Agregar 4 nuevos comandos al bot de Telegram

## Resumen

Extender homelab-bot con 4 nuevos comandos que exploren métricas avanzadas del sistema:
- `/bateria` — estado actual y tiempo restante
- `/procesos` — top 5 procesos por consumo combinado (CPU + RAM)
- `/internet` — velocidad de conexión (download, upload, ping)
- `/temperatura` — estadísticas de las últimas 24 horas

## Estructura general

### Cambios al código
- Agregar 4 funciones nuevas a `homelab-bot.py` (battery_info, top_processes, internet_speed, temperature_stats)
- Agregar 4 funciones de formato de mensaje (battery_msg, processes_msg, internet_msg, temperature_msg)
- Agregar función de limpieza de datos históricos (cleanup_old_temps)
- Extender `handle()` con 4 nuevos casos de comando
- Modificar `status_msg()` para registrar temperatura cada vez que se consulta

### Persistencia de datos
- Crear archivo `temperature.json` en el mismo directorio que el script
- Formato: array de objetos `{timestamp: int, temp: int}`
- Se escribe cada vez que se llama `/status` o cualquier comando
- Se limpia automáticamente antes de escribir (elimina registros > 24h)

## Nuevos comandos

### `/bateria`
Muestra estado actual de batería y estimado de tiempo restante.

**Salida si está enchufado:**
```
⚡ Batería: 85% · cargando
```

**Salida si está en batería:**
```
🔋 Batería: 42% · en batería
⏱ Tiempo restante estimado: ~4 horas
```

**Cálculo de tiempo restante:**
- Si `/sys/class/power_supply/BAT0/energy_now` existe, se usa para estimar horas restantes
- Fórmula: horas_restantes = energy_now / power_now (si power_now > 0)
- Si no hay datos suficientes o el cálculo es impreciso: no se muestra estimado
- Si está enchufado: no se muestra tiempo restante

### `/procesos`
Muestra los 5 procesos con mayor consumo combinado (CPU% + RAM%).

**Salida:**
```
🔝 Top 5 procesos por consumo

1. firefox
   CPU: 12.5% | RAM: 1240MB

2. python3
   CPU: 8.3% | RAM: 856MB

... (3 más)
```

**Implementación:**
- Leer `/proc/[pid]/stat` para CPU
- Leer `/proc/[pid]/status` para RSS (RAM)
- Calcular CPU% usando tiempo total del sistema
- Sumar ambos para ranking

### `/internet`
Mide velocidad de conexión a Internet usando speedtest-cli.

**Salida:**
```
🌐 Velocidad de conexión

📥 Download: 125.4 Mbps
📤 Upload: 45.2 Mbps
📡 Ping: 18 ms (8.8.8.8)
```

**Implementación:**
- Usar `speedtest-cli` (ya instalado) para obtener velocidades
- Hacer ping a 8.8.8.8 usando `subprocess` + ping
- Nota: speedtest tarda 30-60 segundos, el usuario espera

**Manejo de errores:**
- Si no hay conexión: "❌ Error: sin conexión a Internet"
- Si speedtest falla: "⚠️ No se pudo medir velocidad"

### `/temperatura`
Muestra estadísticas de temperatura de las últimas 24 horas.

**Salida:**
```
🌡️ Temperatura (últimas 24h)

📈 Máximo: 78°C
📉 Mínimo: 52°C
📊 Promedio: 65°C
🔴 Actual: 72°C

📋 Registros: 24 muestras
```

**Implementación:**
- Leer `temperature.json`
- Filtrar registros de últimas 24h (comparar con `time.time()`)
- Calcular máximo, mínimo, promedio
- Si < 2 registros: "Sin datos (necesita 24h)"

## Persistencia y limpieza

### Archivo `temperature.json`
```json
[
  {"timestamp": 1715000000, "temp": 65},
  {"timestamp": 1715003600, "temp": 68},
  {"timestamp": 1715007200, "temp": 72}
]
```

### Función `cleanup_old_temps()`
- Se ejecuta cada vez antes de guardar temperatura
- Elimina registros con `timestamp < now - 86400` (86400 = 24h en segundos)
- Escribe el array limpio de vuelta a `temperature.json`
- Si el archivo no existe, lo crea vacío

### Cuándo se registra temperatura
- Cada vez que se llama `/status` (comando por defecto)
- Cada vez que se llama `/temperatura`
- Cada vez que se llama `/internet` (como proxy de actividad)

Esto garantiza ~1-3 muestras por hora en uso normal.

## Flujo de ejecución

En `handle()` se agregan 4 casos nuevos:
```python
elif cmd == "/bateria":
    send(ALLOWED_CHAT_ID, battery_msg())
elif cmd == "/procesos":
    send(ALLOWED_CHAT_ID, processes_msg())
elif cmd == "/internet":
    send(ALLOWED_CHAT_ID, internet_msg())
elif cmd == "/temperatura":
    send(ALLOWED_CHAT_ID, temperature_msg())
```

Cada función de mensaje llama a `register_temperature()` al final para registrar el dato.

## Manejo de errores

Cada nueva función tiene try-except que devuelve un mensaje de error claro:
- Lectura de `/proc` fallida → "❌ Error leyendo procesos"
- Speedtest fallido → "⚠️ No se pudo medir velocidad"
- JSON corrupto → "❌ Error leyendo datos históricos"
- Comando lento (speedtest) → se notifica al usuario que espere

## Actualización de `/help`

Se agrega al mensaje de ayuda:
```
/status       — estado del sistema (default)
/docker       — detalle de contenedores
/bateria      — estado de batería y tiempo restante
/procesos     — top 5 procesos por consumo
/internet     — velocidad de conexión
/temperatura  — máx/mín/promedio últimas 24h
/help         — este mensaje
```

## Consideraciones técnicas

### Rendimiento
- Speedtest es lento (30-60s): se ejecuta en el hilo principal. El usuario espera.
- Lectura de `/proc` es rápida (< 100ms)
- Limpieza de histórico es O(n) pero n es pequeño (24 registros máximo)

### Robustez
- Si `temperature.json` no existe, se crea al primer registro
- Si está corrupto, se resetea (pierde histórico pero no falla)
- Cada comando es independiente; error en uno no afecta otros

### Compatibilidad
- Todo funciona en cualquier Linux (Debian 12, Ubuntu, Fedora, etc.)
- Requiere `speedtest-cli` instalado (ya está)
- Usa solo stdlib + dependencias existentes

## Siguientes pasos

1. Escribir las 4 funciones nuevas en `homelab-bot.py`
2. Implementar persistencia con `temperature.json`
3. Actualizar `handle()` y `/help`
4. Probar cada comando manualmente
5. Commit y deploy
