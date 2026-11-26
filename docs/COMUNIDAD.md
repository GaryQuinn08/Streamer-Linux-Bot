# Habilitar cuentas y aportes de la comunidad

El sitio conserva dos partes: **Galería** (colección curada en GitHub, sin
cuenta) y **Comunidad** (aportes de creadores con Google). La página de
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
   y pulsa **Run** una sola vez en el proyecto nuevo.
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
   `docs/comunidad/index.html`, añade el origen exacto de ese proyecto
   a `connect-src`. **Nunca** publiques una clave `service_role`,
   `sb_secret_`, el secreto de Google ni tokens de sesiones.
5. Publica por la rama de Pages. Primero prueba con dos cuentas Google
   permitidas: cada una debe ver solo sus propios aportes; una visita
   sin cuenta debe poder descargar diseños aprobados, pero no acceder
   a pendientes, enviarlos ni aprobarlos.

## Revisar propuestas

El archivo HTML original nunca se aloja. El editor vuelve a leer solo
los datos reconocidos del archivo, incluidos CSS y animaciones compatibles.
La web genera la nueva previsualización aislada y un HTML al descargar;
no ejecuta scripts aportados. Aun así, abre y revisa cada propuesta,
verifica el crédito y la licencia y no apruebes material que no quieras
publicar. El nombre de crédito es elegido por el creador, y no equivale a
un nombre verificado. Su identidad de Google no es pública.

Desde el SQL Editor del proyecto, busca los pendientes:

```sql
select id, creator_name, description, license, design, created_at
from public.overlay_submissions
where status = 'pending'
order by created_at;
```

Una vez revisado un aporte, puedes publicarlo o retirarlo:

```sql
select public.review_overlay_submission('UUID-DEL-APORTE'::uuid, true);
-- Sustituye true por false para rechazar o retirar un diseño.
```

Solo un mantenedor con acceso al proyecto puede ejecutar la revisión.
Eliminar la cuenta en Supabase borra sus propuestas y publicaciones
asociadas; las copias que otras personas ya descargaron no se retiran.
Antes de abrir envíos a todo el mundo, define un contacto para
privacidad y retiradas, y publica el aviso correspondiente.
