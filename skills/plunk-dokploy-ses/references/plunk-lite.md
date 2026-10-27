# Plunk Lite: la imagen ligera (opcional)

## Índice
1. Qué es
2. En qué se diferencia de la imagen oficial
3. Cuándo recomendarla y cuándo no
4. Desplegar con Plunk Lite
5. Actualizar
6. Volver a la imagen oficial

## 1. Qué es

[Plunk Lite](https://github.com/joanproductivo/plunk-lite) es un fork **no oficial** de Plunk pensado solo para self-hosting. Lo mantiene una persona, no el equipo de Plunk. Parte de una versión de Plunk (hoy, la 0.17.0) y le añade arreglos que aún no están en la oficial, además de una imagen más pequeña.

La imagen se publica en `ghcr.io/joanproductivo/plunk-lite`, es pública y tiene la misma licencia que Plunk (AGPL-3.0). Usa la misma base de datos y las mismas variables que la oficial: se puede pasar de una a otra cambiando la imagen del compose.

## 2. En qué se diferencia de la imagen oficial

| | Oficial (con el arranque recortado del compose) | Plunk Lite |
|---|---|---|
| Node.js | 20 (sin parches de seguridad desde abril de 2026) | 24 |
| Procesos | nginx, api, worker y el panel con su propio servidor Node | nginx, api y worker; nginx sirve el panel como ficheros estáticos |
| Landing, wiki, relay SMTP | Van en la imagen; el compose los apaga al arrancar | No van en la imagen |
| Tamaño de la imagen | ~1,7 GB | ~0,9 GB |
| Memoria del contenedor | ~190–230 MB | ~190 MB recién arrancado (Node 24 gasta algo más por proceso, pero no hay proceso del panel) |
| Analítica de Plunk en el panel | Sí (carga un script de terceros en cada visita) | No |

Además lleva arreglos de fallos que la oficial aún no tiene. Por ejemplo, las aperturas automáticas que SES marca como tales ya no cuentan, las tasas del dashboard son correctas, cancelar un workflow detiene sus esperas y los nombres con acentos o emojis salen bien en las cabeceras y los adjuntos. También adelanta arreglos de la próxima versión de Plunk (0.18.0). El detalle está en los commits del repositorio.

Y añade funciones que la oficial no tiene:

- **Editor de emails.** Los estilos se aplican en línea al enviar, para que el email se vea igual en Gmail y Outlook, y los envíos de prueba salen con el mismo aspecto. Hay campo de texto de vista previa (preheader); bloques de botón, divisor, espaciador, vídeo de YouTube (tres tamaños) y caja con fondo; menú `/` para insertarlos; galería de imágenes subidas; enlaces a archivos subidos (PDF, Word, Excel o PowerPoint, hasta 9,9 MB) desde un botón o un texto, con su galería «My files»; estilos de marca del proyecto (tipografía, colores, fondo, ancho, botón por defecto y esquinas redondeadas) y pie de baja editable por idioma. En pantallas anchas, el editor y sus ajustes quedan uno al lado del otro, con la vista previa como pestaña.
- **Contactos.** Exportar a CSV; importar con la fecha de alta original y asignando segmentos, también desde un CSV exportado de Flodesk; la selección masiva respeta el filtro activo.
- **Segmentos estáticos.** Lanzan eventos de entrada y salida que pueden arrancar workflows, y se gestionan en bloque desde Contactos, desde la ficha de cada contacto y desde los workflows (paso «Update contact» y condición de pertenencia). Se pueden borrar varios a la vez, salvo los que usa otro segmento o una campaña activa.
- **Avisos.** Un banner en el panel y emails a las direcciones de Settings → Alerts cuando un email no se puede enviar, cuando falla una campaña o un workflow, cuando el proyecto se desactiva, cuando la tasa de rebotes o quejas se acerca a los límites de AWS y cuando SES deja de verificar un dominio.

Estas funciones guardan sus datos en cuatro tablas propias (`plunk_lite_*`). Las tablas de Plunk no cambian, así que la imagen oficial arranca sobre la misma base de datos; simplemente ignora esas tablas (sección 6).

También es más segura al enviar en volumen. Revisada en octubre de 2026 antes de campañas de miles de emails:

- **Rebotes y quejas.** No se pierden (el webhook pide a SNS que reintente si falla) ni se cuentan dos veces.
- **Reintentos de envío.** Un email que SES no aceptó se reintenta, y uno que aceptó nunca se reenvía.
- **Suscripción.** Se vuelve a comprobar justo antes de enviar.
- **Campañas.** Repetir un lote o pulsar dos veces «Enviar» no duplica emails.
- **Tasa de rebotes.** Se mide sobre lo enviado y corta donde AWS revisa la cuenta (5 % de rebotes, 0,1 % de quejas).
- **Emails atascados.** Un barrido los cierra sin enviar nada dos veces.
- **Apagado.** El api y el worker tienen hasta 30 s para terminar lo que tienen en curso.
- **Envío a SES sin reintentos ocultos.** El SDK de AWS reintentaba por su cuenta un corte de conexión y podía duplicar un email que SES ya había aceptado. Ahora hay un solo intento, con tiempos límite, y solo se reintenta lo que SES rechazó o lo que nunca llegó a conectar.
- **Rebotes de alias y reenvíos.** Dan de baja al contacto aunque SES nombre la dirección final.
- **Eventos en cola.** Entregas, aperturas y clics los procesa el worker, 5 a la vez, en lugar del webhook. Una campaña grande ya no satura la base de datos, y las copias repetidas de SNS se descartan.
- **Adjuntos guardados.** La limpieza diaria vacía, pasados 90 días, los adjuntos de los emails junto con su cuerpo. Antes se quedaban para siempre en la base de datos.
- **Abuso.** Las peticiones tienen un tamaño máximo de 2 MB (10 MB en `/v1/send`, y solo 8 grandes a la vez), el login admite 10 intentos cada 15 minutos por email, y cada proceso tiene un techo de memoria.

## 3. Cuándo recomendarla y cuándo no

**Recomiéndala** si la persona:
- quiere gastar menos memoria y disco en un servidor pequeño;
- prefiere un Node.js con soporte de seguridad;
- no necesita el relay SMTP de Plunk (enviar desde otro programa por SMTP en vez de por la API).

**No la recomiendes** si:
- necesita el relay SMTP: Plunk Lite no lo lleva;
- quiere solo software del proyecto oficial o soporte del equipo de Plunk;
- necesita una versión de Plunk que Plunk Lite aún no ha incorporado. Plunk Lite sigue a la oficial con algo de retraso.

Explica las dos opciones en una frase cada una y deja elegir a la persona. Si duda, la oficial con el arranque recortado es la opción por defecto.

## 4. Desplegar con Plunk Lite

Sigue la Fase 1 de SKILL.md con estos cambios en `assets/docker-compose.yml`, antes de crear el compose en Dokploy:

1. Averigua cuál es hoy la última Plunk Lite:
   ```bash
   python3 scripts/plunk_lite_latest.py
   ```
   Imprime la etiqueta para el compose (`ghcr.io/joanproductivo/plunk-lite:sha-<commit>`), el commit y la fecha de compilación. No necesita Docker ni credenciales. Sin Python, la misma información está en la página del paquete: https://github.com/joanproductivo/plunk-lite/pkgs/container/plunk-lite
2. Pon esa etiqueta en la imagen del servicio `plunk`:
   ```yaml
   image: ghcr.io/joanproductivo/plunk-lite:sha-<commit>
   ```
   Plunk Lite publica cada versión como `sha-<commit>` y, además, la más reciente como `latest` (sale de la rama `plunk-lite` del repositorio). En el compose usa siempre la `sha-<commit>`, no `latest`: con `latest`, cualquier despliegue o reinicio del servidor podría cambiar de versión sin que nadie lo decida y sin copia previa de la base de datos.
3. Borra el bloque `entrypoint`/`command` del servicio `plunk`, con sus tres líneas de comentario. La imagen ya arranca solo lo necesario. Si se deja, no rompe nada, pero sobra.

El resto no cambia: el env (con las variables `S3_*` del bucket), los dominios, SES y el DNS.

**Verificación** (sustituye a la de la Fase 1):
- El contenedor `plunk` queda healthy.
- En el log no aparece `Plunk: arrancando…`. En su lugar, pm2 arranca exactamente tres procesos: `App [nginx:0] online`, `App [api:1] online` y `App [worker:2] online`.
- En el log aparecen `nginx: configuration file /etc/nginx/nginx.conf test is successful` y `URL replacement complete for web`. Si la configuración de nginx o el reemplazo de URLs fallan, el contenedor se para a propósito, en vez de quedarse a medias.
- `https://envio-api.<dominio>/health` responde 200 y `https://envio.<dominio>` muestra el login.

## 5. Actualizar

1. Ejecuta `python3 scripts/plunk_lite_latest.py` (sección 4). Si la etiqueta coincide con la del compose, ya está al día. Si no, lee en el repositorio qué cambió entre los dos commits: `https://github.com/joanproductivo/plunk-lite/compare/<commit instalado>...<commit nuevo>`.
2. Haz una copia de Postgres (operations.md §5).
3. Cambia la etiqueta de la imagen en el compose y despliega.
4. Verifica como en la sección 4. Si algo falla, vuelve a la etiqueta anterior con el mismo compose.

## 6. Volver a la imagen oficial

Antes, avisa de lo que se pierde si se han usado las funciones propias (sección 2):

- **Emails hechos con el editor de Plunk Lite.** La oficial ignora la marca, el preheader y los pies propios. El botón, el divisor, el espaciador, los vídeos y las cajas con fondo pueden verse peor, sobre todo en Outlook, y el editor oficial abre como HTML los emails con cajas. Revisa las plantillas y las campañas que se vayan a reutilizar.
- **Workflows con segmentos estáticos.** En la oficial, los segmentos estáticos dejan de lanzar sus eventos de entrada y salida, así que los workflows que arrancan con ellos se quedan parados. Además, un paso «Update contact» que solo cambia segmentos hace fallar la ejecución, y una condición de pertenencia a segmento va siempre por «no».
- **Avisos.** Dejan de llegar.

Los datos no se borran: quedan en las tablas `plunk_lite_*` y vuelven a usarse si se regresa a Plunk Lite.

1. Haz una copia de Postgres.
2. Pon la imagen oficial (`ghcr.io/useplunk/plunk:<versión>`) en una versión igual o más nueva que la base de Plunk Lite. Si eliges una más antigua, la base de datos podría tener migraciones que esa versión no conoce.
3. Vuelve a poner el bloque `entrypoint`/`command` de `assets/docker-compose.yml`, o el contenedor arrancará también landing, wiki y SMTP.
4. Despliega y verifica como en la Fase 1 de SKILL.md.
