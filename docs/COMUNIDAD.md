# Habilitar cuentas y aportes de la comunidad

El sitio conserva dos partes: **Galería** (colección curada en GitHub, sin
cuenta) y **Comunidad** (aportes de creadores con Google). La página de
Comunidad mantiene el aporte por GitHub hasta que configures Supabase.
No se usan contraseñas propias ni se comparten correos de Google.

## Configuración de producción

1. En [Supabase](https://supabase.com/dashboard), crea un proyecto que
   controles. En el **SQL Editor**, ejecuta el archivo
   `supabase/migrations/202611260501_overlay_community.sql` del repo una
   sola vez en ese proyecto. Esto crea las tablas, los permisos y la función
   que usa el mantenedor para aprobar. No pegar el SQL en el proyecto equivocado.
2. En Supabase, **Authentication → URL Configuration**, registra la URL
   de la comunidad como **Site URL** y **Redirect URL**:
   `https://garyquinn08.github.io/Streamer-Linux-Bot/comunidad/`.
3. En Google Cloud crea un cliente OAuth **Aplicación web** aparte del
   cliente de escritorio de YouTube. Configura **Google** en Supabase con
   la URL de retorno que te muestra su proveedor, por ejemplo
   `https://TU-REFERENCIA.supabase.co/auth/v1/callback`. Configura allí
   el ID y secreto de Google; no se agregan a GitHub ni se envían por chat.
   Consulta la [guía oficial de Supabase para Google](https://supabase.com/docs/guides/auth/social-sign-in/auth-google).
4. Edita `docs/comunidad/config.js` con la **Project URL** sin barra final
   y la clave que empieza con **`sb_publishable_`**. En el CSP de
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
