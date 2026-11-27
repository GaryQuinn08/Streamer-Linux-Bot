# Habilitar cuentas y aportes de la comunidad

La **Galería** se puede explorar sin cuenta. En **Mi cuenta** puedes iniciar sesión con
Google y personalizar tu perfil; en **Comunidad** puedes ver o publicar aportes. La página de
Comunidad mantiene el aporte por GitHub hasta que configures Supabase.
No se usan contraseñas propias ni se comparten correos de Google.

## Configuración de producción

1. En [Supabase → New project](https://supabase.com/dashboard/new), usa
   una organización que controles. Para una primera prueba basta el plan
   gratuito. Crea `streamer-linux-bot` en una región cercana y guarda la
   contraseña de la base de datos en tu gestor de contraseñas. No es una
   contraseña que necesiten el sitio web, OBS ni quienes usan la app.
   Deja **Enable Data API** activado, con `public` entre los esquemas
   expuestos, pero deja **Automatically expose new tables** desactivado:
   la migración concede solo los permisos que necesita la comunidad.
   [Permisos de la API de Supabase](https://supabase.com/docs/guides/api/securing-your-api).
   En **SQL Editor → New query**, pega el contenido completo de la
   [migración de la comunidad](../supabase/migrations/202611260501_overlay_community.sql)
   y pulsa **Run** una sola vez en el proyecto nuevo. Después aplica una vez la
   [migración de publicación y estadísticas](../supabase/migrations/202611260550_overlay_catalog.sql).
   En una instalación que ya tenga la primera, aplica solo la segunda.
2. En Supabase, **Authentication → URL Configuration**, registra la URL
   de la comunidad como **Site URL** y **Redirect URL**:
   `https://garyquinn08.github.io/Streamer-Linux-Bot/comunidad/`.
3. En Supabase abre **Authentication → Sign In / Providers → Google** y
   copia la **Callback URL** que aparece. En [Google Auth Platform](https://console.cloud.google.com/auth/clients),
   crea un cliente OAuth **Aplicación web** aparte del cliente de escritorio
   de YouTube. Agrega `https://garyquinn08.github.io` como origen de
   JavaScript autorizado (sin la ruta) y la **Callback URL** de Supabase como
   URI de redirección autorizada (por ejemplo,
   `https://TU-REFERENCIA.supabase.co/auth/v1/callback`). Si la audiencia de
   Google sigue en modo de prueba, agrega las cuentas que usarás para probar.
   Regresa al proveedor Google de Supabase, actívalo y guarda ahí el ID y el
   secreto del cliente. No envíes el secreto por chat ni lo subas a GitHub.
   Consulta la [guía oficial de Supabase para Google](https://supabase.com/docs/guides/auth/social-sign-in/auth-google).
4. Copia la **Project URL** sin barra final desde el panel **Connect** y la
   clave que empieza con **`sb_publishable_`** desde **Settings → API Keys**.
   Son los únicos dos valores que van en `docs/comunidad/config.js`. En el CSP de
   `docs/comunidad/index.html`, `docs/galeria/index.html` y `docs/cuenta/index.html`, añade el origen exacto de ese proyecto
   a `connect-src`. **Nunca** publiques una clave `service_role`,
   `sb_secret_`, el secreto de Google ni tokens de sesiones.
5. Publica por la rama de Pages. Primero prueba con dos cuentas Google:
   cada una debe ver solo sus propios aportes en «Mis aportes» y poder
   cambiar su voto sin contarse dos veces. Una visita sin cuenta debe poder
   explorar y descargar, pero no subir, votar ni consultar aportes privados.

## Publicación y estadísticas

Los nuevos diseños se publican de inmediato, sin aprobación previa.
El servidor conserva solo ajustes visuales y animaciones que reconoce.
No aloja el archivo HTML original ni publica HTML, CSS o JavaScript
personalizado; el editor vuelve a generar un HTML compatible al descargar.
El crédito público lo elige la persona creadora y no equivale a una
identidad verificada. No se muestra el correo de Google.

**Puntuación:** se muestra el promedio y el número de votos. Cada cuenta
Google tiene un voto editable de 1 a 5 por diseño. **Descargas:** se
cuentan las descargas iniciadas desde la Galería y Comunidad, sin exigir
cuenta. No se cuenta una previsualización, no se guardan IP ni correos
para las estadísticas y no se reconstruyen las descargas anteriores a
esta función. No es un número de personas únicas.

## Retirar publicaciones

Las propuestas ya pendientes antes del cambio conservan su estado y
siguen privadas. Desde el SQL Editor del proyecto, un mantenedor puede
retirar un diseño publicado, o aprobar uno de esos pendientes:

```sql
select public.review_overlay_submission('UUID-DEL-APORTE'::uuid, false);
-- Solo para publicar un aporte anterior pendiente, usa true.
```

Eliminar una cuenta en Supabase borra sus propuestas, publicaciones y
votos asociados; las copias que otras personas ya descargaron no se
retiran.

## Perfiles y temas

Tras instalar las migraciones anteriores, aplica una sola vez
[`202611260610_overlay_profiles_packs.sql`](../supabase/migrations/202611260610_overlay_profiles_packs.sql).
Desde **Mi cuenta** se puede guardar el nombre público y la biografía privada sin subir archivos.
El inicio de sesión iniciado ahí vuelve al panel a través de la ruta de Comunidad ya autorizada. Activar el modo editor es voluntario
y no concede permisos de moderación. Solo el dueño ve el perfil; al publicar se usa
su alias como crédito. Consulta [Temas y paquetes](TEMAS.md) para el flujo de archivos.
