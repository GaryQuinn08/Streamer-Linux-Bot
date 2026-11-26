# Conectores de eventos

Los conectores externos de esta beta requieren pruebas con cuentas en
directo. No pegues tokens en chats, capturas, issues ni en el repositorio.
Los botones de **Inicio** muestran el estado y **Registro** muestra errores
sin imprimir las credenciales.

## TikTok LIVE: dos posibilidades

- **TikTok directo**: ejecuta `bash instalar.sh --tiktok` en el clon.
  En Inicio elige el conector directo e introduce el @usuario que ya esté
  en vivo. Recibe regalos terminados, seguidores y chat (incluye comandos
  que comienzan con `!`). Usa la biblioteca de terceros [TikTokLive](https://github.com/isaackogan/TikTokLive),
  sin solicitar contraseña; el servicio de firma externo puede limitar
  conexiones o romperse. En servidor: `servidor --tiktok directo --canal @usuario`.
- **TikFinity**: activa su [Event API](https://tikfinity.com/) en la máquina
  que corre TikFinity. El bot lee `ws://127.0.0.1:21213/`; en Linux, usa
  un túnel privado desde esa máquina si TikFinity vive en Windows. Por
  ejemplo, desde Windows: `ssh -N -o ExitOnForwardFailure=yes -R 127.0.0.1:21213:127.0.0.1:21213 usuario@servidor`.
  El bot utiliza esa API local, no instala TikFinity. En servidor:
  `servidor --tiktok tikfinity`. No ejecutes ambos conectores para el
  mismo directo simultáneamente.

## Iniciar sesión desde la app

En **Inicio → Twitch / YouTube**, pulsa **Iniciar sesión**. El bot abre el
navegador predeterminado en el sitio oficial y, al autorizar, vuelve al
bot automáticamente. No pegues tokens en la app. Las autorizaciones solo
se guardan en memoria mientras dura la conexión. Si vence el token,
vuelve a iniciar sesión. El bot recuerda únicamente el Client ID público
de Twitch y la ruta local al archivo de cliente de Google, no su contenido.
Para cambiar de cliente o proyecto, usa **Configurar…**.

### Twitch: configuración por primera vez

1. En la [consola de Twitch Developers](https://dev.twitch.tv/console/apps)
   registra una aplicación de tipo **Public** con la URL de redireccionamiento
   exacta `http://localhost:17845/oauth/twitch`. No necesitas Client Secret.
2. En la app pulsa **Iniciar sesión en Twitch**, introduce el **Client ID**
   que te dio Twitch y autoriza con la cuenta dueña de tu canal. El bot
   obtiene el ID de tu canal y se conecta a EventSub.
3. Si el puerto 17845 está en uso, no cierres procesos ajenos: revisa si
   otra copia está iniciando sesión. Este puerto es local y distinto al
   del catálogo.

Se solicitan permisos de lectura `user:read:chat`, `moderator:read:followers`,
`channel:read:subscriptions`, `bits:read` y `channel:read:redemptions`.
Algunos eventos no están disponibles para todos los canales.

### YouTube: configuración por primera vez

1. En Google Cloud habilita **YouTube Data API v3** y crea un
   [cliente OAuth de tipo Aplicación de escritorio](https://console.cloud.google.com/auth/clients).
   Configura la pantalla de consentimiento y, si el proyecto está en modo
   Pruebas, agrega tu cuenta como usuario de prueba.
2. Descarga el JSON del cliente, guárdalo en tu equipo (no en Git) y
   selecciónalo en **Iniciar sesión en YouTube**.
3. En Google elige la cuenta o canal que tiene el directo y autoriza el
   acceso de lectura. El bot busca el directo activo más reciente que tenga
   chat. No ejecuta acciones por chat histórico. Recibe chat, Super Chat,
   Super Stickers y nuevas membresías.

Para cuentas públicas necesitarías distribuir Client IDs de aplicaciones
propias y, según los permisos y la plataforma, completar su verificación.
Esta beta no incluye identificadores de proyectos de terceros.

### Servidor sin interfaz

El modo `servidor` conserva las variables de entorno, sin abrir navegador.
Para Twitch usa `--twitch` con `SLB_TWITCH_CLIENT_ID`, `SLB_TWITCH_BROADCASTER_ID`
y `SLB_TWITCH_TOKEN`. Para YouTube usa `--youtube` con `SLB_YOUTUBE_TOKEN`
y `SLB_YOUTUBE_LIVE_CHAT_ID`. Introduce los tokens localmente; evita
dejarlos en el historial de la terminal o en archivos del repositorio.

## Kick (webhook firmado, solo servidor)

1. Instala el extra: `bash instalar.sh --servidor --kick`.
2. Descarga la clave pública PEM **actual** desde el
   [endpoint oficial de Kick](https://api.kick.com/public/v1/public-key)
   y guarda solo la clave pública en un archivo `kick.pem`. Vuelve a
   descargarla y reinicia el bot si Kick la rota.
3. Inicia `~/.local/bin/streamer-linux-bot-server servidor --kick-clave /ruta/kick.pem --kick-canal ID_NUMERICO`.
   Abre exclusivamente `POST /webhooks/kick` mediante un proxy HTTPS con
   límites de solicitudes y tamaño; destino interno `127.0.0.1:8770`.
   No publiques el puerto del catálogo. El receptor verifica la firma,
   vigencia, canal y duplicados.
4. Registra esa URL en tu app de desarrollador Kick y suscribe los
   eventos mediante la [API oficial de eventos](https://github.com/KickEngineering/KickDevDocs/blob/main/events/introduction.md)
   con el permiso `events:subscribe`. El bot **recibe** los webhooks;
   no gestiona OAuth ni registra suscripciones. Eventos soportados:
   `chat.message.sent`, `channel.followed`, `channel.subscription.new`,
   `channel.subscription.renewal` y `kicks.gifted`.

Esta versión solo recibe eventos; no publica mensajes por sí sola.
