# OBS, TikTok LIVE Studio y modo servidor

## Dos opciones para transmitir

- **OBS Studio (Linux):** en Overlays copia la URL de una alerta.
  En OBS añade una Fuente de navegador con esa URL. Eso basta para ver la
  alerta. Para que una acción cambie una escena o visibilidad, habilita
  WebSocket v5 en OBS y conecta **Conexiones → OBS Studio** por separado.
- **TikTok LIVE Studio:** en el equipo con LIVE Studio, comprueba primero
  que la URL abre en su navegador. Luego selecciona **Añadir fuente →
  Enlace**, pega la URL de una alerta (no la del catálogo) y ajusta el
  tamaño de la fuente. Comprueba con una alerta de prueba antes de salir en
  vivo. La opción Enlace depende de la cuenta y la versión; no se ha
  validado todavía en un LIVE Studio real. Consulta la
  [guía de fuentes Enlace de TikFinity](https://blog.tikfinity.com/how-to-use-tiktok-live-studio/).
  Si tu versión no muestra Enlace o no admite el enlace local, no abras el
  puerto al público: usa OBS para componer el video y prueba su cámara
  virtual como fuente de LIVE Studio. La cámara virtual solo lleva video;
  configura el audio por separado en LIVE Studio.

## Multichat: panel privado y overlay para el directo

En **Overlays → Chat multiplataforma** hay dos salidas distintas:

- **Panel privado de chat para OBS.** Pulsa **Copiar enlace del panel privado**.
  En OBS, abre **Paneles → Paneles de navegador personalizados** (*Docks →
  Custom Browser Docks*), crea un panel y pega el enlace. El panel siempre
  escribe la plataforma junto al mensaje e incluye todas las plataformas
  conectadas; los filtros del overlay no le afectan. Es de solo lectura.
  No agregues su enlace como fuente ni lo compartas. Si OBS no ofrece ese tipo
  de panel, el botón **Abrir panel en navegador** permite usarlo en privado.
- **Overlay del directo.** En los ajustes puedes mostrar el nombre del
  espectador y la etiqueta de plataforma por separado, personalizar el color
  de Twitch (morado por defecto), TikTok (gris), YouTube y Kick, y aplicarlo
  al borde o al nombre. Guarda los cambios para verlos en las fuentes abiertas.
  Como antes, **Actualizar el navegador cuando la escena se active** limpia los
  mensajes anteriores al volver a la escena.

**Plataforma de este enlace** permite copiar una fuente separada, p. ej. **Solo
Twitch**. Solo cambia el enlace que estás copiando: puedes usar otro para TikTok
y conservar el panel privado con ambos chats. Si envías la misma escena a dos
destinos, no pongas un overlay con chats combinados en la salida de Twitch
durante un simulcast. [Directrices de Twitch](https://help.twitch.tv/s/article/simulcasting-guidelines?language=es_MX).
El bot no activa el simulcast ni inicia la emisión.

## Modo servidor de Linux, sin escritorio

Dentro del clon, en la máquina Linux que ejecutará el bot:

```bash
bash instalar.sh --servidor --tiktok
~/.local/bin/streamer-linux-bot-server servidor --puerto 8765 --simular gift --espera 30
```

`--tiktok` es opcional; para recibir un directo real cambia los argumentos
por `--tiktok directo --canal @tu_usuario`. Si solo quieres el servidor
sin Qt en Mint, Ubuntu o Debian, los únicos paquetes del sistema para el
arranque básico son `git`, Python 3.11+ y `python3-venv`. Por ejemplo, una
máquina Debian 13 ya provisionada puede ejecutar el bot como usuario sin sudo.
En un servicio remoto usa un perfil dedicado y ejecuta como usuario sin
privilegios. `Ctrl+C` detiene el servidor limpiamente.

Desde la PC de transmisión (PowerShell o terminal con OpenSSH), abre y
mantén activo el túnel:

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:8765:127.0.0.1:8765 usuario@servidor
```

Ya puedes abrir `http://127.0.0.1:8765/` **en la PC de transmisión**. Copia
la alerta seleccionada a OBS o LIVE Studio. Si el puerto 8765 de la PC
está ocupado, usa por ejemplo `-L 127.0.0.1:18765:127.0.0.1:8765` y abre
`http://127.0.0.1:18765/`. No reemplaza ni cierra el otro proceso.
Los puertos permanecen privados; no abras el del catálogo en el router.

### Administrar reglas en el servidor

El servidor recibe eventos sin Qt. Para editar reglas con la misma interfaz,
instala también la variante de escritorio en el servidor (`bash instalar.sh`)
y usa el editor de perfil. Desde una PC Linux con X11/XWayland, el reenvío
gráfico requiere que tu servidor SSH ya tenga X11 forwarding y `xauth`
habilitados:

```bash
ssh -X usuario@servidor '~/.local/bin/streamer-linux-bot configurar'
```

Ese editor no abre puertos ni activa conexiones. Si no tienes reenvío
gráfico, edita `config.json` por SSH. Tras guardar y cerrar el editor,
envía `SIGHUP` **solo** al PID de tu bot servidor (`kill -HUP PID`) para
recargar las reglas, acciones y estilos, o reinícialo. Identifica el PID
con tu gestor de servicios o con el que registraste al iniciar el
proceso; no envíes la señal a otros procesos. Si cambiaste un estilo,
recarga la fuente en OBS o LIVE Studio. Los ajustes de conexiones y puertos
requieren reinicio. No hay cliente gráfico remoto nativo para Windows en
esta beta. El sonido y el TTS se reproducen donde corre el bot, no en un
agente remoto.

Para que un bot remoto controle OBS en la PC de transmisión sin publicar
OBS en la red, **desde la PC de transmisión** abre, junto al túnel local,
un túnel inverso de loopback:

```bash
ssh -N -o ExitOnForwardFailure=yes -R 127.0.0.1:14455:127.0.0.1:4455 usuario@servidor
```

En el archivo del servidor configura `settings.obs.host` a `127.0.0.1` y
`settings.obs.port` a `14455`. Alimenta `SLB_OBS_PASSWORD` solo en la sesión
del servidor (no en Git ni en el archivo) y arráncalo con `--obs`. Este
túnel no aporta control de escenas a LIVE Studio.
