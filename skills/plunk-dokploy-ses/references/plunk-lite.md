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
- **API.** `/v1/track` admite también la clave secreta (`sk_`), así que un formulario que llama desde su servidor da el alta y registra el evento en una sola llamada. `/v1/track` y `/v1/send` aceptan `segments`, hasta 20 segmentos estáticos a los que se añade el contacto en la misma llamada, con sus eventos de entrada (en `/v1/track`, solo con la `sk_`). Detalle en using-plunk.md §3.
- **MCP.** Su MCP lleva herramientas para los segmentos estáticos y avisa de los dados de baja en las campañas TRANSACTIONAL. Para usarlo desde claude.ai, el compose de mcp-remote.md lo compila en el mismo commit que la imagen (§2 de ese fichero).
- **Segmentos estáticos.** Lanzan eventos de entrada y salida que pueden arrancar workflows, y se gestionan en bloque desde Contactos, desde la ficha de cada contacto y desde los workflows (paso «Update contact» y condición de pertenencia). Se pueden borrar varios a la vez, salvo los que usa otro segmento o una campaña activa.
- **Avisos.** Un banner en el panel y emails a las direcciones de Settings → Alerts cuando un email no se puede enviar, cuando falla una campaña o un workflow, cuando el proyecto se desactiva, cuando la tasa de rebotes o quejas se acerca a los límites de AWS y cuando SES deja de verificar un dominio.
- **Bajas por rebote o queja.** Un rebote permanente o una queja que da de baja a un contacto suscrito (o en pausa) lanza `contact.unsubscribed` con `reason` `bounce` o `complaint`, justo después de `email.bounce` o `email.complaint`. Así un solo workflow con disparador `contact.unsubscribed` y un paso Webhook mantiene al día las bajas en otra web. En las estadísticas cuenta como baja además de como rebote o queja, y una sola vez en las sumas (contactos perdidos de la campaña y Net de Audiencia).
- **Doble opt-in.** Interruptor por proyecto en Settings → Brand, apagado por defecto. Con él, un alta por la API (`/v1/track` o `POST /contacts` con clave, o `/v1/send` con `subscribed: true`) deja el contacto sin suscribir y le manda un email de confirmación, editable por idioma. Hasta que pulsa el enlace sale como «Pending confirmation» (filtro propio en Contactos, sin caducidad) y no recibe marketing; al confirmar se suscribe, lanza `contact.subscribed` y entra en los `segments` del alta. La `pk_` no manda confirmaciones. Topes por contacto (1 cada 15 minutos, 3 al día) y por proyecto, con aviso. Además, haya o no doble opt-in: añadir a un segmento nunca suscribe, un email entrante no vuelve a suscribir a un contacto existente y solo un contacto suscrito puede pausar sus emails. Detalle en using-plunk.md §3.
- **Webhooks firmados.** El paso Webhook de un workflow puede llevar un secreto propio, para que quien recibe la petición compruebe que viene de Plunk.
  - **Poner el secreto:** quien recibe lo genera y lo pone con `PUT /workflows/<id>/steps/<stepId>/signing-secret`, con la `sk_` y `{"secret": "<32 a 256 caracteres ASCII imprimibles, sin espacios>"}`. Conviene crear el workflow apagado, añadir el paso, poner el secreto y encenderlo después, para que no salga ningún aviso sin firmar.
  - **Lo que lleva cada petición:** `X-Plunk-Signature: t=<segundos unix>,v1=<hex HMAC-SHA256 de "<t>." + el cuerpo tal como se envía>`. Con GET se firma `"<t>."`.
  - **Comprobarla:** el receptor recalcula la firma sobre los bytes crudos, compara en tiempo constante y rechaza un `t` a más de 5 minutos de su reloj.
  - **El secreto no se puede leer:** `GET` en la misma ruta solo dice si hay uno, y `DELETE` lo quita. Duplicar el workflow no lo copia: el duplicado sale sin firma.
  - **Una respuesta que no sea 2xx** hace fallar el paso y avisa. No se reintenta, así que el receptor debe responder 2xx también a lo repetido o ya hecho.

Estas funciones guardan sus datos en nueve tablas propias (`plunk_lite_*`). Las tablas de Plunk no cambian, así que la imagen oficial arranca sobre la misma base de datos; simplemente ignora esas tablas (sección 6).

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
- **Rebotes y avisos (lote E2).** Cada envío lleva etiquetas de SES: un rebote o una queja encuentra su email aunque falte el `messageId`, y se suprime la dirección aunque no haya fila. Frenos por fuente (campaña cancelada, workflow desactivado) y el proyecto solo como último recurso; botón para reactivarlo con 7 días de gracia. Avisos también con el proyecto desactivado, comprobación cada 15 min de que llegan los eventos de SES, y alarmas de CloudWatch en el banner si su topic se suscribe al webhook. Borrar contactos no baja las tasas (tabla propia `plunk_lite_deleted_email_counts`).
- **Revisión del lote E2.** Los contactos borrados se cuentan por minuto (reactivar y limpiar la lista no vuelve a desactivar), la comprobación de reputación no pierde avisos y se acota sin Redis, y el mensaje de prueba de SES y el topic `plunk-alarmas` no dan avisos falsos.
- **API y plataforma (lote E4).**
  - **Límites de la API pública:** `data` de hasta 32 KB y 6 niveles, de 1 a 50 destinatarios por `/v1/send`, 200 campos y 64 KB por contacto, y lo que Postgres no puede guardar da 422 en vez de 500.
  - **`/v1/send` con varios destinatarios** responde 207 con `failed` en vez de cortarse en el primero que falla.
  - **Altas verificadas** (`PLUNK_LITE_VERIFY_SIGNUPS`, activado). Un contacto nuevo por la API recibe 422 `INVALID_EMAIL`, con la dirección sugerida, si su dominio no existe, no recibe correo, es desechable o es una errata de un gran proveedor (`gmial.com`). Ante la duda del DNS, la deja pasar.
  - **`PLUNK_LITE_PUBLIC_TRACK=off`** apaga la clave pública (403). `/v1/track` sigue funcionando con la secreta desde un servidor.
  - **Proyectos y claves:** un proyecto desactivado o con las claves regeneradas se nota al instante, y las claves inventadas no llegan a la base de datos.
  - **Menos carga:** `api_requests` escribe menos y está acotado; los CSV de importación no se quedan en Redis.
  - **Arranque:** la API se reinicia sola si no arranca, y hay un aviso si Redis se acerca a su techo de memoria.
- **Workflows (lote E3).**
  - Un job repetido no reenvía el email de su paso, y DELAY tras DELAY funciona.
  - Una ejecución cancelada o fallida no vuelve a moverse.
  - Una espera y su ejecución se escriben juntas, y el evento o el tiempo límite las reclaman juntas.
  - Cada 5 minutos un barrido recupera las ejecuciones que nada despertaba: vuelve a programar el fin de un DELAY o de una espera que se perdió, y da por fallidas, con aviso, las que se quedaron a medias.
- **Envío resiliente (lote E1).**
  - El envío se adapta a lo que SES dice de toda la cuenta, sin gastar los intentos de cada email: con el límite de ritmo espera un segundo, con la cuota diaria agotada espera un cuarto de hora, y con la cuenta pausada pausa la cola y lo vuelve a probar cada 30 minutos. La cuota y la pausa salen en los avisos como «Amazon SES».
  - Para saber si SES ha pausado la cuenta lee su estado, con el permiso `ses:GetAccount` que añade `ses_setup` (aws-ses.md §1), y además lo deduce de los rechazos. Sin el permiso, solo lo deduce, y una pausa con un texto que no conoce puede pasar inadvertida mientras envía un solo dominio.
  - Un email que SES rechaza por sí mismo (una dirección o un remitente sin verificar) falla en el acto, sin reintentos.
  - Una campaña que no cabe en el 95 % de la cuota de 24 horas se rechaza al empezar, contando lo que les falta a las campañas en curso; el otro 5 % queda para transaccionales y workflows.
  - Los emails de una ejecución de workflow cancelada no salen, aunque ya estuvieran en la cola.
  - Un lote de campaña que falla del todo se reintenta hasta 3 rondas más, y el panel avisa de cuántos dados de baja recibe una campaña TRANSACTIONAL.
- **Protección CSRF.** Las peticiones de escritura con la cookie del panel solo se aceptan si su `Origin` es el panel.
- **Lista de supresión propia.** Guarda las direcciones con un rebote permanente o una queja, y las que una importación marca como `bounced`, `cleaned` o `complained` (como el CSV de Flodesk). Nunca se les envía nada, tampoco transaccionales, y nada las vuelve a suscribir: un evento, un envío o una importación las deja dadas de baja, y una petición explícita (dar de alta el contacto desde el panel o marcarlo como suscrito) responde 409 `ADDRESS_SUPPRESSED`. Solo la ficha del contacto en el panel, o la propia persona desde un email que recibió, levantan la supresión.
  - En Contactos salen como «Suppressed», con el motivo, y tienen filtro propio, que respetan «select all», las acciones en bloque y la exportación (hasta 20.000 por proyecto). En el CSV, su `status` es `bounced` o `complained`, y al importarlo vuelven a la lista.
  - La lista de SES es de toda la cuenta. «Remove suppression» en la ficha pide confirmación y la saca también de ahí, salvo que venga de una importación. Desde el enlace de un email, solo se saca tras un rebote que SES intentó de verdad, nunca una queja: SES no dice por qué tiene bloqueada una dirección. Con la lista de SES sin limpiar, el siguiente envío rebota y la dirección vuelve a suprimirse.
- **Reenviar una campaña cancelada.** Tras cancelar, ningún lote del envío anterior crea más emails, y la campaña solo vuelve a borrador cuando ya no le queda ninguno. Si SES pudo aceptar alguno de los que fallaron, se queda cancelada para no enviar dos veces. Reprogramar una campaña cambia de verdad su hora.
- **Eventos en cola.** Entregas, aperturas y clics los procesa el worker, 5 a la vez, en lugar del webhook. Una campaña grande ya no satura la base de datos, y las copias repetidas de SNS se descartan.
- **Adjuntos guardados.** La limpieza diaria vacía, pasados 90 días, los adjuntos de los emails junto con su cuerpo. Antes se quedaban para siempre en la base de datos.
- **Abuso.** Las peticiones tienen un tamaño máximo de 2 MB (10 MB en `/v1/send`, y solo 8 grandes a la vez), el login admite 10 intentos cada 15 minutos por email (sin que un `_` en la dirección valga de comodín), y cada proceso tiene un techo de memoria.
- **La DLQ se vacía sola.** Lo que SNS no consigue entregar al webhook (una caída de más de unos 40 minutos) queda 14 días en la cola `plunk-ses-events-dlq` (aws-ses.md §10). Plunk Lite la lee cuando salta su alarma `ses-eventos-dlq`, cada 15 minutos y desde el botón «Process AWS dead-letter queue now» de Settings → Alerts, y pasa cada mensaje por el mismo webhook, con su firma y su cuenta comprobadas:
  - procesa los rebotes y las quejas; descarta las entregas, aperturas y clics de más de 24 horas, que contarían dos veces;
  - un fallo pasajero vuelve a la cola, cada vez más tarde, y nunca se borra mientras la base de datos, Redis o AWS estén caídos;
  - el rebote o la queja recuperados salen marcados en la actividad del contacto, y cada proyecto ve en un aviso lo que se recuperó para él;
  - necesita el statement `PlunkDLQ` que añade `ses_setup` (aws-ses.md §1). Sin él, todos los paneles avisan «AWS dead-letter queue not readable».

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
- En el log, `Dead-letter queue worker started`.

**Probar el vaciado de la DLQ** (cuando ya estén hechas la Fase 2 y la Fase 3, con `ses_setup`, la suscripción confirmada y el dominio de envío verificado; mejor también con las alarmas de `ses_alarms` y `PANEL=si`). Comprueba de punta a punta que un rebote que SNS no consiguió entregar no se pierde. Con el permiso de la persona:
1. Desde Plunk, crea el contacto suscrito `success@simulator.amazonses.com`, con un dato que lo marque como prueba (`plunk_create_contact`, o `POST /contacts`), y envíale un email desde el dominio de envío (`plunk_send_email`, o `/v1/send`). Apunta el id del email que devuelve el envío y el del proyecto. Se usa `success@` y no `bounce@`: `bounce@` manda el rebote en vivo, y el de la DLQ sería una copia ya registrada.
2. Ejecuta `scripts/dlq_test.snippet.py` con `REGION`, `ACCOUNT_ID`, `EMAIL_ID`, `PROJECT_ID` y `FROM` (el remitente del paso 1). Necesita una identidad con permisos de administración de SNS y SQS, no la de `plunk-ses`. Crea un topic y dos colas temporales para que SNS firme un rebote de ese email, lo deja en `plunk-ses-events-dlq` y borra lo temporal al terminar, también si falla. Debe acabar con `rebote firmado en plunk-ses-events-dlq` y `recursos temporales borrados`.
3. En unos 3 minutos (2,5 medidos) salta la alarma `ses-eventos-dlq` y su aviso lanza el vaciado. Sin alarmas, o si ya estaba en ALARM, lo hace la comprobación de cada 15 minutos. En el log de `plunk` deben salir `Permanent bounce received for success@simulator.amazonses.com` y `[DLQ] Drained: 1 handled, 0 dropped as too old, 0 left for later, 0 given up on`.
4. **Comprueba:**
   - la DLQ queda vacía (`ApproximateNumberOfMessages` y `ApproximateNumberOfMessagesNotVisible` a 0);
   - el contacto queda de baja; no se suprime, porque es una dirección del simulador;
   - en su ficha, el rebote lleva «Recovered from the AWS dead-letter queue», y la baja, «Removed after a hard bounce»;
   - el panel muestra el aviso «AWS dead-letter queue» con `Handled: 1 bounce`, y el de la alarma se cierra solo.
5. La persona borra el contacto de prueba.

Si en el paso 3 sale `[DLQ] Not allowed`, falta el statement `PlunkDLQ`: vuelve a ejecutar `ses_setup`.

## 5. Actualizar

1. Ejecuta `python3 scripts/plunk_lite_latest.py` (sección 4). Si la etiqueta coincide con la del compose, ya está al día. Si no, lee en el repositorio qué cambió entre los dos commits: `https://github.com/joanproductivo/plunk-lite/compare/<commit instalado>...<commit nuevo>`.
2. Haz una copia de Postgres (operations.md §5).
3. Si la política de IAM no tiene aún `ses:GetAccount` o `ses:DeleteSuppressedDestination` (`ses_check` lo muestra en `iam.missing_actions`) o el statement `PlunkDLQ` con que Plunk Lite vacía la DLQ (`iam.missing_dlq_actions`), ejecuta `ses_setup` otra vez antes de desplegar. Sin `PlunkDLQ`, todos los paneles avisan «AWS dead-letter queue not readable» y la DLQ no se vacía.
4. Cambia la etiqueta de la imagen en el compose y despliega. Si usas el MCP remoto, regenera su compose con el commit nuevo y despliégalo también (mcp-remote.md §8). Si cambian también los `command` de Postgres o Redis (como en la versión con el lote E4), Docker los recrea y la instalación se corta alrededor de un minuto: despliega fuera de una campaña.
5. Verifica como en la sección 4. Si algo falla, vuelve a la etiqueta anterior con el mismo compose.

## 6. Volver a la imagen oficial

Antes, avisa de lo que se pierde si se han usado las funciones propias (sección 2):

- **Emails hechos con el editor de Plunk Lite.** La oficial ignora la marca, el preheader y los pies propios. El botón, el divisor, el espaciador, los vídeos y las cajas con fondo pueden verse peor, sobre todo en Outlook, y el editor oficial abre como HTML los emails con cajas. Revisa las plantillas y las campañas que se vayan a reutilizar.
- **Workflows con segmentos estáticos.** En la oficial, los segmentos estáticos dejan de lanzar sus eventos de entrada y salida, así que los workflows que arrancan con ellos se quedan parados. Además, un paso «Update contact» que solo cambia segmentos hace fallar la ejecución, y una condición de pertenencia a segmento va siempre por «no».
- **Avisos.** Dejan de llegar.
- **Webhooks firmados.** Salen sin firma. El receptor que la exige los rechaza y la oficial da el paso por bueno con cualquier respuesta, así que esos avisos se pierden sin alerta: apaga antes esos workflows. Volver a una Plunk Lite anterior a esta función tiene el mismo efecto.
- **Bajas por rebote o queja.** Vuelven a dar de baja sin lanzar `contact.unsubscribed`: un workflow de bajas deja de enterarse de ellas.
- **Doble opt-in.** Desaparece: los contactos pendientes siguen sin suscribir, sus enlaces de confirmación dejan de funcionar, y `/v1/track` y añadir a un segmento vuelven a suscribir directamente. Apágalo antes y decide qué hacer con los pendientes.
- **API.** Un `/v1/send` con varios destinatarios vuelve a cortarse en el primero que falla (sin 207), las altas con un email que no recibe correo vuelven a entrar, y las variables `PLUNK_LITE_*` se ignoran.
  - Un `/v1/track` con la clave secreta da 401: el formulario que la use tiene que pasar a la `pk_`, o a `POST /contacts` y `POST /events/track`.
  - El campo `segments` se ignora sin error: los contactos no entran en esos segmentos.
- **DLQ de eventos de SES.** Deja de vaciarse sola: hay que reenviar a mano al webhook lo que quede (aws-ses.md §10), y la alarma `ses-eventos-dlq` se queda en ALARM hasta entonces. El statement `PlunkDLQ` puede quedarse.
- **MCP remoto.** Vuelve al de npm: regenera su compose sin `--plunk-lite` (mcp-remote.md §2). El de Plunk Lite pide rutas que la oficial no tiene.
- **Trabajos en bloque.** Antes de cambiar de imagen, comprueba que la cola `bulk-contact-actions` de Redis no tiene trabajos pendientes o por reintentar con el filtro «Suppressed», o vacíala: la oficial, y las imágenes de Plunk Lite anteriores a ese filtro, no lo conocen y seleccionarían **todos los contactos** del proyecto, también en un borrado.
- **Lista de supresión propia.** La oficial no la conoce: una importación o una llamada a `/v1/track` puede volver a suscribir a quien rebotó o se quejó. La supresión de la cuenta de SES sigue bloqueando esos envíos, pero cuentan como intentos. Antes de importar contactos, quita esas direcciones del CSV.

Los datos no se borran: quedan en las tablas `plunk_lite_*` y vuelven a usarse si se regresa a Plunk Lite.

1. Haz una copia de Postgres.
2. Pon la imagen oficial (`ghcr.io/useplunk/plunk:<versión>`) en una versión igual o más nueva que la base de Plunk Lite. Si eliges una más antigua, la base de datos podría tener migraciones que esa versión no conoce.
3. Vuelve a poner el bloque `entrypoint`/`command` de `assets/docker-compose.yml`, o el contenedor arrancará también landing, wiki y SMTP.
4. Despliega y verifica como en la Fase 1 de SKILL.md.
