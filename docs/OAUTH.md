# Habilitar las conexiones como mantenedor

El streamer no registra aplicaciones ni pega tokens. El responsable de
Streamer Linux Bot registra y configura los clientes OAuth **una vez por
proyecto y por entorno de distribución**. Una vez instalado un cliente
válido, **Conectar** abre el navegador del sistema, donde el streamer
elige su cuenta y autoriza. El bot no intercepta contraseñas.

## Registro y pruebas

| Plataforma | Registro de la aplicación | Retorno |
| --- | --- | --- |
| Twitch | [Twitch Developers](https://dev.twitch.tv/console/apps): cliente **Public**. | `http://localhost:17845/oauth/twitch` |
| YouTube | [Google Cloud](https://console.cloud.google.com/auth/clients): cliente **Aplicación de escritorio**, YouTube Data API v3 y consentimiento configurado. | IP loopback con puerto dinámico para clientes de escritorio. |
| Spotify (solo uso privado) | [Spotify for Developers](https://developer.spotify.com/dashboard): una app con Web API. En modo Desarrollo, agrega expresamente las cuentas de prueba. | `http://127.0.0.1:17846/oauth/spotify` |

Para YouTube en modo Pruebas, incluye las cuentas de prueba. Antes de
distribuir, completa el proceso de verificación de Google si lo requieren
el tipo de proyecto y los permisos. En Spotify, consulta sus
[modos de acceso y cuotas](https://developer.spotify.com/documentation/web-api/concepts/quota-modes)
y su [política de desarrolladores](https://developer.spotify.com/policy).
La función del bot no mezcla, graba ni retransmite Spotify.

## Aprovisionamiento (solo mantenedor)

Puedes preparar en el perfil de la instalación el archivo
`~/.config/streamer-linux-bot/oauth-clients.json` (si usas
`XDG_CONFIG_HOME` o `SLB_CONFIG_DIR`, respeta esa ruta). Copia
`docs/oauth-clients.example.json`, completa los identificadores públicos,
y ajusta `google_client_file` para referenciar el JSON OAuth de escritorio
fuera del repositorio. Puede ser una ruta absoluta o relativa a
`oauth-clients.json`. Restringe los permisos del JSON de Google y no lo
incluyas en Git, mensajes ni capturas. No hay credenciales de servicios
incluidas en el código fuente. La distribución pública sin configuración
manual queda pendiente hasta que esos clientes estén registrados y
aprovisionados en la instalación.

Para pruebas también puedes configurar `SLB_TWITCH_CLIENT_ID`,
`SLB_GOOGLE_CLIENT_JSON` (ruta al archivo) y `SLB_SPOTIFY_CLIENT_ID` en el
entorno del lanzador. No se guardan tokens en esos archivos. Reinicia el
bot tras modificar el aprovisionamiento. El registro y verificación
pertenecen al titular del proyecto; este bot no crea registros afuera ni
solicita a los streamers credenciales de desarrollador.

## Controles de seguridad

Las autorizaciones salen al navegador del sistema, usan PKCE S256 y un
estado aleatorio. El retorno TCP solo se abre en loopback mientras se
autoriza. No expongas esos puertos en un túnel ni a Internet. No hay
renovación automática en esta versión; ante sesión vencida, Conectar
abre el navegador de nuevo. Cerrar o desconectar libera la sesión local;
si quieres revocar todo acceso, usa los controles de tu cuenta en el
proveedor.
