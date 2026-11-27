# Condiciones y variables locales (beta 20)

Desde **Acciones → Subacciones** puedes añadir:

- **Guardar variable local**. Por ejemplo, escribe `saludo` como nombre y
  `Hola, {user}` como valor. Usa `{local_saludo}` en las subacciones que
  siguen, por ejemplo en un registro, una alerta o el TTS. El valor se crea
  durante esa ejecución y no se guarda al cerrar. Dos ejecuciones en paralelo
  no comparten valores.
- **Si / Si no**. Elige una variable sin llaves, por ejemplo `count` o
  `local_saludo`, un operador y el valor de comparación. Para comparar contra
  otra variable, sí usa llaves en el valor. Puedes elegir una acción para
  cada resultado o dejar uno como **No hacer nada**. La acción original
  continúa después de la rama.
- **Ejecutar otra acción aquí**. Elige una acción por su nombre. Conserva el
  evento y las variables locales; los cambios de la acción llamada se pueden
  usar en los pasos posteriores. Se mantiene el turno de la acción original,
  incluso si ambas pertenecen a la misma cola. El historial muestra una sola
  ejecución. Cancelarla detiene también los pasos pendientes de la llamada.

Las comparaciones de texto son exactas salvo que elijas ignorar mayúsculas.
Los operadores numéricos comparan números, no el orden del texto
(`10` es mayor que `2`); usa punto para decimales. Si la variable no existe,
o el valor no es un número válido en una comparación numérica, se elige
**Si no**. Para distinguir una variable ausente de una vacía, usa **Existe**
o **No existe**.

## Prueba con un regalo simulado

1. Crea una acción **Mensaje de regalo**. Dale la cola **Alertas**, y agrega
   **Guardar variable local**: nombre `saludo`, valor `Gracias, {user}`.
2. Crea otra acción **Regalo grande** con la misma cola **Alertas**. Agrega
   **Si / Si no**: variable `count`, comparación **Es mayor o igual (número)**,
   valor `3`. En **Si se cumple** elige **Mensaje de regalo**; deja **Si no**
   en **No hacer nada**.
3. Después de la condición, agrega **Escribir en Registro** con
   `{local_saludo}`. Pulsa **Ejecutar con regalo de prueba** (tres unidades).
   Verás `Gracias, viewer_demo` en **Registro**, y una sola ejecución en
   **Historial**. Si cambias la condición a **Es mayor que (número)**, la
   rama no se ejecuta y el registro deja `{local_saludo}` sin sustituir.

El editor rechaza llamadas circulares. Si quieres eliminar una acción
reutilizada, quita primero sus referencias. Una ejecución admite hasta
12 acciones anidadas y 512 pasos en total. No hay código libre ni variables
globales o persistentes en este bloque. Las variables locales solo salen en
una alerta si las colocas explícitamente en su texto; el envío automático
de datos al overlay sigue limitado a los campos de evento admitidos.
