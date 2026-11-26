# Streamer Linux Bot (v2)

Aplicación de escritorio para Linux que automatiza tu stream: recibe eventos
(chat, seguidores, regalos, donaciones...), los pasa por **triggers** y ejecuta
**acciones** (alertas en pantalla, cambios de escena en OBS, sonidos, TTS...).

## Beta 4 para Linux

Instalación desde el repositorio sin ZIP ni dependencias de Qt de APT.
Conserva el perfil de la beta anterior, incluido el catálogo y las alertas
importadas. Cierra la app anterior antes de abrir la nueva.

El espacio de automatización pone **Acciones, Triggers y Subacciones**
juntos. Las conexiones, el catálogo, la música y el registro tienen su
propia sección. TikTok directo no necesita TikFinity ni inicio de sesión:
funciona con el @ en directo y el conector opcional no oficial.

### Linux Mint, Ubuntu o Debian

Si faltan paquetes del sistema:

```bash
sudo apt install git python3-venv libegl1 libgl1 libxcb-cursor0 \
  libxkbcommon-x11-0 libxcb-icccm4 libxcb-keysyms1 libxcb-xinerama0
```

Luego usa el código de la rama de prueba (esta versión aún no está en `main`):

```bash
git clone -b refactor/overlay-boundary https://github.com/GaryQuinn08/Streamer-Linux-Bot.git
cd Streamer-Linux-Bot
bash instalar.sh --tiktok
~/.local/bin/streamer-linux-bot
```

Quita `--tiktok` si solo usarás el simulador o el puente TikFinity.
El instalador descarga dependencias de PyPI en un entorno privado, crea un
acceso en el menú y no necesita sudo. Si ya clonaste esa rama, actualiza
con `git pull --ff-only` y vuelve a ejecutar el instalador. El comando
estable apunta a la instalación más reciente; no borra versiones anteriores.

### Servidor, LIVE Studio y conectores

- [OBS, TikTok LIVE Studio y modo servidor por SSH](docs/TRANSMISION.md).
- [TikTok / TikFinity, Twitch, YouTube y Kick](docs/CONECTORES.md).
- [Música, sonido y Piper](docs/AUDIO.md).
- [Configurar clientes OAuth como mantenedor](docs/OAUTH.md).

El control de escenas y fuentes usa el WebSocket v5 de **OBS Studio**.
En **TikTok LIVE Studio** la integración es por una fuente **Enlace**, no
control de escenas. El bot sigue siendo Linux: la PC donde corre LIVE Studio
puede recibir las alertas del servidor Linux a través de un túnel privado.
Falta probar esa ruta en LIVE Studio real y validar eventos de cuentas reales.

### Empaquetado y desarrollo

```bash
sh packaging/debian/build.sh                       # genera dist/*.deb para Debian 13
sh packaging/portable/build.sh                     # genera ZIP alternativo
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run.py
```

## Probar que todo funciona

1. Abre la app y ve a **Conexiones**.
2. Pulsa **Regalo (TikTok)**: se dispara el trigger "Regalo de TikTok", que
   ejecuta la acción "Alerta de regalo". Verás las líneas en **Registro**.
3. Ve a **Overlays**, elige "Alerta de regalos", pulsa **Abrir en el navegador**
   y vuelve a pulsar un evento de prueba: la tarjeta animada aparece en la página.
4. En **Overlays**, copia la URL de una alerta. En OBS usa **Fuentes → + → Navegador**.
   En LIVE Studio prueba **Añadir fuente → Enlace** si tu cuenta tiene esa opción.

Pruebas automáticas:

```bash
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

## Cómo fluye un evento

```
Conector o botón de prueba (Qt) → Event → EventBus ─┬→ Engine → triggers → acciones
                                                  └→ Actividad → overlay integrado de últimos eventos
Una acción "overlay_alert" envía una alerta solo al overlay seleccionado.
```

## Catálogo, alertas y puerto

- En **Conexiones** abre **Abrir catálogo de alertas** para ver las alertas
  incluidas, creadas e importadas en la misma página de siempre.
- En **Overlays** puedes ajustar valores como color, duración y tamaño,
  guardarlos y probar la alerta. La URL no cambia al guardar: actualiza la
  fuente de OBS. Si tu URL antigua trae parámetros después de `?`, esos
  parámetros prevalecen; copia la URL limpia para usar lo guardado.
- **Nueva alerta** crea una copia editable de la alerta animada. Selecciónala
  en **Regla de regalos → Mostrar en** para usarla con la regla de regalos.
- Se aceptan ZIP o carpetas con `manifest.json` e `index.html`, y HTML
  independiente. El HTML antiguo se muestra, pero no recibe eventos
  automáticamente sin adaptarlo al SDK; no se convierten exportaciones
  propietarias de otras aplicaciones.
- Si el puerto anterior está ocupado, abre igual la ventana y deja el campo
  en blanco. Escribe otro puerto en **Conexiones → Puerto de overlays**.
  Solo se guarda cuando el servidor consigue escucharlo. Si cambias un
  puerto activo, actualiza su URL en OBS una sola vez.

## Automatización sin editar JSON

En **Acciones**, elige o crea una acción a la izquierda. A la derecha se
ven sus **Disparadores** y sus **Subacciones**: agrega qué inicia la acción,
qué pasos ejecuta y en qué orden. Por ejemplo, un regalo puede mostrar
una alerta, cambiar la escena en OBS y reproducir un sonido. El botón de
prueba usa un regalo simulado, pero ejecuta los pasos reales configurados.
También tienes una vista global de **Disparadores** y una **Regla de
regalos** rápida para TikTok.

## Configuración

`~/.config/streamer-linux-bot/config.json` (se crea al primer arranque).
Contiene ajustes, triggers y acciones. El archivo se guarda con permisos
600 y no incluye la contraseña de OBS.

Ejemplo de trigger:

```json
{
  "id": "tiktok-rosas",
  "name": "Rosas grandes",
  "platform": "tiktok",
  "event_type": "gift",
  "filters": { "gift_name": "Rose", "min_value": 5 },
  "cooldown_s": 10,
  "action_id": "alert-gift"
}
```

Filtros disponibles: `min_value`, `gift_name`, `user`, `contains` (texto del
mensaje), `command`.

Pasos de acción disponibles: `log`, `wait`, `overlay_alert`, `obs_scene`,
`obs_source_visible`, `play_sound`, `tts`, `music_queue_add` (archivos locales),
`chat_message` (pendiente). En los textos puedes usar `{user}`, `{platform}`,
`{type}` y los campos del evento (`{gift_name}`, `{count}`, `{amount}`...).

## Crear tu propio overlay

Crea una carpeta en `~/.local/share/streamer-linux-bot/overlays/<id>/` con:

```
manifest.json   id, name, description y params (opciones editables)
index.html      carga /sdk/overlay-sdk.js y tu script.js
style.css, script.js
```

Copia `slbot/overlays/builtin/gift-alert/` como punto de partida. Dentro del
script usa el SDK:

```js
const color = SLB.param("color", "#ff4d8d");            // opciones desde la URL
SLB.onAlert("mi-overlay", (msg) => { /* msg.title, msg.text */ });
```

El SDK se conecta a `/ws/<id>` según la URL del overlay; las URLs de las fuentes de
navegador en OBS no cambian. Los overlays propios reciben las alertas que las
acciones les dirigen. El feed integrado de últimos eventos es el único
suscriptor de actividad de plataforma, con datos limitados a los campos que
muestra. Si un overlay propio usaba `SLB.onEvent` o se conectaba directamente a
`/ws`, cámbialo para recibir alertas dirigidas con el SDK actualizado.

Regla de seguridad: muestra siempre nombres y mensajes con `textContent`, nunca
con `innerHTML`.

## Seguridad

- El servidor escucha solo en `127.0.0.1` y rechaza peticiones con `Origin` o
  `Host` que no sean locales.
- El servidor de overlays es de lectura: la simulación se inicia desde la ventana nativa.
- Los identificadores de los overlays integrados están reservados.
- Los overlays importados no se ejecutan en un entorno aislado. Ejecutan JavaScript dentro de OBS: importa solo los
  de gente de confianza (la app lo avisa antes de importar).
