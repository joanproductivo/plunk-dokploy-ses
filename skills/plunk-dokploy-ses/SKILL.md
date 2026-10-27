---
name: plunk-dokploy-ses
description: Despliega y configura Plunk self-hosted (useplunk/plunk, email marketing y transaccional open source) en Dokploy con AWS SES, de principio a fin. Incluye un compose probado y recortado en memoria, dominios con Traefik y Let's Encrypt, usuario IAM mínimo, configuration sets y SNS para eventos, registros DNS con las trampas de Cloudflare, salida del sandbox de SES y plan de precios. También cubre el envío desde una web por API (/v1/send, /v1/track), workflows, aperturas falsas, mantenimiento y el MCP de Plunk publicado con login para usarlo desde claude.ai. Permite usar la imagen oficial o Plunk Lite, un fork ligero no oficial. Úsala siempre que alguien quiera instalar, revisar, actualizar o arreglar Plunk en Dokploy o Docker con SES. También para conectar Plunk a AWS SES, verificar un dominio de envío, pedir producción en SES para Plunk o mandar emails de su web a través de Plunk, aunque no mencione Dokploy ni esta skill. En inglés también aplica (self-host Plunk, Plunk on Dokploy, Plunk SES setup).
---

# Plunk en Dokploy con AWS SES

Guía para montar una instalación privada de Plunk que envía a través de AWS SES, desplegada como compose en Dokploy. Sale de dos instalaciones reales (Plunk 0.17.0, octubre de 2026, DNS en Cloudflare, SES en eu-north-1). Funciona igual con otras regiones y otros proveedores de DNS.

Al terminar, la persona tiene:
- un panel en `https://envio.<dominio>`;
- una API en `https://envio-api.<dominio>`;
- las imágenes del editor en un bucket de Cloudflare R2 (u otro S3), servidas en `https://envio-files.<dominio>`;
- uno o varios dominios de envío verificados;
- los eventos de SES (entregas, rebotes, quejas, clics) llegando a Plunk;
- los registros cerrados.

## Cómo trabajar

- **Habla en el idioma de la persona y sin jerga.** Muchas de las personas que instalan esto no son técnicas: explica qué hace cada paso en una frase, no cómo funciona por dentro.
- **Comprueba cada fase antes de pasar a la siguiente.** Cada fase tiene su verificación. Si saltas una, el error aparece dos fases después y cuesta más encontrarlo.
- **Secretos:**
  - Los secretos internos (base de datos, JWT) los generas tú con `scripts/render_env.py`. El archivo queda con permisos 600 y nunca muestras sus valores.
  - Las **access keys de AWS** y las **claves del token del bucket** (R2 u otro S3) las crea la persona y las pega directamente en Dokploy. No le pidas que las pegue en el chat ni las crees tú: no deben pasar por la conversación.
  - Una vez pegadas, **no vuelvas a escribir el env por la API de Dokploy**. Dokploy devuelve los secretos ocultos, y guardar ese env sustituiría las claves reales. A partir de ahí, cualquier cambio de variables lo hace la persona en la interfaz.
- **Acciones hacia fuera, solo con un sí explícito:**
  - pedir a AWS la salida del sandbox;
  - cambiar el plan de precios de SES;
  - borrar dominios, volúmenes o identidades;
  - publicar algo en GitHub.
- **Herramientas:**
  - Con el MCP de Dokploy, usa sus herramientas (`compose-create`, `compose-update`, `domain-create`, `compose-deploy`, `compose-readLogs`…). Sin él, guía a la persona por la interfaz.
  - Con el MCP oficial de AWS, ejecuta los snippets con `run_script`. Sin él, usa `scripts/run_snippet.py` con un perfil del AWS CLI. Sin ninguno de los dos, guíala por la consola.

## Fase 0: Decidir antes de tocar nada

Pregunta solo lo que no sepas ya:

1. **¿Cuántas cuentas de AWS?** Una instalación de Plunk usa **una sola** cuenta de SES para todos sus proyectos: las credenciales son de la instalación, no del proyecto. Si dos personas o empresas quieren factura y reputación de envío separadas, hacen falta dos instalaciones. Pueden ir en el mismo servidor (operations.md §10).
2. **Dominio de la instalación y prefijo.** Por ejemplo `envio`, `envio-api` y `envio-files` bajo un dominio que se vaya a conservar.
   - El dominio del panel aparece en los enlaces de baja y en las imágenes de todos los emails. Cambiarlo después obliga a mantener el viejo meses (operations.md §8).
   - Si varias marcas comparten instalación, todas verán ese dominio.
   - Usa un solo nivel de subdominio, porque el certificado gratuito de Cloudflare no cubre más.
3. **Dominio de envío.** Recomienda un subdominio dedicado (`news.<dominio>`), distinto de los tres de la instalación (dns.md §3).
4. **Región de SES.** La de la cuenta de AWS. Se usa la misma en todo.
5. **Buzón para respuestas.** Plunk no recibe correo. Comprueba que la dirección de respuesta tiene un buzón que funcione (using-plunk.md §7).
6. **Dónde guardar las imágenes del editor.** Plunk las sube a un almacenamiento S3 y las enlaza en los emails. La plantilla no lleva MinIO: usa un bucket externo, por defecto Cloudflare R2 (10 GB gratis, sin coste de salida, y no gasta memoria del servidor). La persona crea el bucket, conecta `envio-files.<dominio>` como dominio propio del bucket (en R2: Settings → Custom Domains; hace público el bucket) y crea un token con lectura y escritura solo en ese bucket. Apunta el endpoint (`https://<account_id>.r2.cloudflarestorage.com`) y el nombre del bucket; las claves del token se pegan en Dokploy en la Fase 2. Si no quiere un servicio externo, ver operations.md §6 (MinIO en el servidor o sin subidas).
7. **Imagen oficial o Plunk Lite.** Por defecto se usa la imagen oficial de Plunk con el arranque recortado del compose. Plunk Lite es un fork ligero y no oficial, con Node 24, la mitad de tamaño, arreglos que la oficial aún no tiene y funciones propias (editor de emails ampliado, segmentos estáticos con eventos, avisos de fallos), pero sin relay SMTP. Explícalo en una frase y pregúntalo solo si a la persona le importan la memoria, la seguridad de Node, esos arreglos o esas funciones (references/plunk-lite.md §2-3).

## Fase 1: Desplegar en Dokploy

1. Genera el env:
   ```bash
   python3 scripts/render_env.py --domain <dominio> --prefix envio --region <región> \
       --s3-endpoint https://<account_id>.r2.cloudflarestorage.com --s3-bucket <bucket> --out plunk.env
   ```
   Las cinco variables del bucket (`S3_ENDPOINT`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_ACCESS_KEY_SECRET`, `S3_PUBLIC_URL`) van siempre en el env, nunca escritas en el compose. Las dos claves quedan vacías: mientras lo estén, Plunk arranca sin subidas de imágenes y sin errores.
   Guárdalo donde la persona tenga su proyecto, no en un sitio público ni en un repositorio.
2. Crea el compose en el proyecto de Dokploy que diga la persona: tipo docker-compose, origen raw y nombre `plunk`.
3. Actualiza el compose con el contenido de `assets/docker-compose.yml` y con **isolatedDeployment activado**. Así Postgres y Redis quedan en una red privada que solo ve Plunk.
   - El compose ya fija la versión de Plunk. Si hay una más nueva, sigue antes operations.md §3.
   - Con Plunk Lite, cambia antes la imagen por la última `sha-<commit>`, que da `scripts/plunk_lite_latest.py`, y quita el bloque `entrypoint`/`command` (references/plunk-lite.md §4).
   - Postgres y Redis van dentro del compose a propósito: aislamiento, arranque en orden (Plunk migra la base al arrancar) y un solo bloque que desplegar.
4. Guarda el env con el contenido de `plunk.env`. Ahora sí puedes hacerlo por la API, porque aún no hay claves de AWS.
5. Crea los dos dominios, con HTTPS, Let's Encrypt y path `/`:

   | Dominio | Servicio | Puerto |
   |---|---|---|
   | `envio.<dominio>` | `plunk` | 80 |
   | `envio-api.<dominio>` | `plunk` | 80 |

   `envio-files.<dominio>` no va en Dokploy: lo sirve el bucket (Fase 0, punto 6).
6. DNS: el panel y la API deben apuntar a la IP del servidor, o estar cubiertos por un comodín. Con Cloudflare pueden ir con proxy, pero en modo SSL **Full** (dns.md §2). El de files lo crea R2 al conectar el dominio propio.
7. Despliega.

**Verificación:**
- El despliegue termina bien y el contenedor `plunk` queda healthy (tarda hasta 90 s en el primer arranque).
- En el log del contenedor `plunk` sale `Plunk: arrancando nginx, api, worker, web`. Con Plunk Lite esa línea no sale: se comprueba como en references/plunk-lite.md §4.
- `https://envio-api.<dominio>/health` responde 200.
- `https://envio.<dominio>` muestra el login.

**Cerrar registros:**
1. La persona crea su cuenta en el panel.
2. Pon `DISABLE_SIGNUPS=true` en el env y despliega. Todavía puedes hacerlo tú, porque aún no hay claves de AWS.
3. Comprueba en el log que solo hubo los registros esperados.

## Fase 2: AWS SES

Lee references/aws-ses.md. En resumen:

1. Ejecuta `scripts/ses_setup.snippet.py` con:
   - la región;
   - el ID de la cuenta;
   - la IP pública del servidor (en el MCP, `settings-getIp`);
   - el dominio de la API.

   Crea un usuario IAM sin claves y con permisos mínimos (solo desde esa IP y esa región), el topic SNS, los dos configuration sets y la suscripción a `https://<API>/webhooks/sns`. La API debe responder ya, porque Plunk confirma la suscripción en el momento.
2. La persona crea la access key de `plunk-ses` y la pega en Dokploy, con los pasos de aws-ses.md §3. En el mismo momento pega las claves del token del bucket en `S3_ACCESS_KEY_ID` y `S3_ACCESS_KEY_SECRET`. Después despliega.
3. **Verificación:**
   - El log de `plunk` muestra `AWS SES quota: 1 emails/second (0/200 emails sent today)`. Eso es el sandbox: las claves funcionan.
   - En la tabla de arranque, `File uploads (S3)` sale `✅`. Con R2 sale además `[S3] Failed to set bucket policy: NotImplemented`: es esperado e inofensivo (R2 no admite esa operación; el bucket ya es público por su dominio propio). Prueba de verdad: la persona sube una imagen en el editor y la URL `https://envio-files.<dominio>/…` se abre desde fuera.
   - `scripts/ses_check.snippet.py` da la suscripción confirmada y una access key activa.
   - Con la suscripción ya confirmada, ejecuta `ses_setup` otra vez: pone los 40 reintentos y la DLQ de la suscripción, que no se pueden poner antes. `ses_check` debe dar `retries: 40`, `dlq` con la cola y `suppressed_reasons` con BOUNCE y COMPLAINT (aws-ses.md §10).
4. **Plan de precios.** Las cuentas nuevas de SES llegan en Essentials (0,16 $ por 1.000 emails). À la carte cuesta 0,10 $ y Plunk ya da las métricas que añade Essentials. Explica la diferencia y cámbialo solo si la persona quiere (aws-ses.md §7).

## Fase 3: Dominio de envío

1. La persona añade el dominio de envío en el panel de Plunk (Settings → Domains). Plunk crea la identidad en SES y muestra 5 registros: 3 CNAME de DKIM, y un MX y un TXT en `plunk.<dominio de envío>`.
2. Ayúdale a crearlos (dns.md §3):
   - **Todos con nube gris.**
   - Créalos en la zona correcta, con el nombre relativo a la zona.
   - Sin el MX opcional de "inbound".
   - Si el dominio no tiene DMARC, añade `v=DMARC1; p=none;`.
3. **Verificación:**
   - `bash scripts/check_dns.sh <dominio de envío> <región> <token1> <token2> <token3>` da todo OK. Los tokens están en Plunk o en `ses_check`.
   - `ses_check` muestra DKIM y MAIL FROM en `SUCCESS`. SES lo recomprueba solo; puede tardar de minutos a horas.
4. **Prueba de envío.** En el sandbox, solo al simulador de SES o a direcciones verificadas (aws-ses.md §5).
   - Envía a las cuatro direcciones del simulador. En el log de `plunk` deben aparecer `Delivery confirmed`, dos `Permanent bounce received` y `Complaint received`: eso confirma toda la cadena SES → SNS → Plunk, rebotes y quejas incluidos.
   - Para ver el email en un buzón real, verifica antes esa dirección en SES y que la persona pulse el enlace (caduca a las 24 h).

## Fase 4: Salir del sandbox

Antes de pedirlo, todo esto tiene que estar listo:
- los dominios en `SUCCESS`;
- DMARC publicado;
- **una web con un formulario de suscripción visible** y enlace a la política de privacidad.

Pide permiso a la persona y confirma con ella:
- el tipo de envío: MARKETING si hay boletines, aunque también haya transaccionales;
- la web;
- el idioma de contacto.

Después haz la petición (aws-ses.md §6).

Si AWS pide más información o la deniega, **no la reenvíes**. La persona responde en el mismo caso de soporte; ayúdale con la plantilla de aws-ses.md §6, rellenada solo con datos ciertos.

Cuando AWS la conceda, **reinicia el contenedor `plunk`**: Plunk lee la cuota de SES solo al arrancar. En el log debe salir la cuota nueva, por ejemplo `14 emails/second (0/50000…)`.

Después, pide a la persona que ponga `EMAIL_RATE_LIMIT_PER_SECOND` un poco por debajo de esa cuota (por ejemplo, `12` con 14/s) en la pestaña Environment, para no rozar el límite de SES.

## Fase 5: Ajustes recomendados

Propón estos ajustes y explica cada uno en una frase. Los cambios de env los hace la persona.

- **Email tracking → "Marketing only"** (Settings → General) si la web va a enviar accesos o códigos por Plunk. Así los antivirus no gastan los enlaces de un solo uso. Contrapartida: el porcentaje de aperturas y clics del dashboard sale más bajo de lo real; los datos fiables están en cada campaña y en Analytics por stream (using-plunk.md §4).
- **Platform emails.** `PLUNK_API_KEY` + `PLUNK_FROM_ADDRESS`; sin ellos, "He olvidado mi contraseña" no envía nada.
- **Límite de peticiones** (`RATE_LIMIT_ENABLED`): viene activado en el compose. Solo hay que tocarlo si una integración propia pasa de 100 eventos o 20 envíos por segundo.
- **Copia diaria de Postgres** a un destino S3/R2 desde Dokploy (operations.md §5).
- **`AUTO_PROJECT_DISABLE=true`** (ya viene así en el env generado). Con Plunk Lite frena primero la campaña o el workflow que rebota, y solo desactiva el proyecto como último recurso (`PLUNK_LITE_DISABLE_*_PERCENT`, ver `references/aws-ses.md`); con la oficial, el crítico desactiva el proyecto. Si la persona lo quiere apagar, que sepa que entonces solo recibe avisos. Recomienda también las alarmas de CloudWatch: `scripts/ses_alarms.snippet.py` (references/aws-ses.md). Los valores de entorno, siempre con punto decimal (`0.4`).
- **No desplegar durante una campaña.** El compose da 45 s para terminar lo que está en curso, pero un despliegue en mitad de un envío grande sigue siendo un riesgo innecesario.
- **Aperturas.** Avisa de que Gmail, Apple y los antivirus generan aperturas falsas: los clics son la métrica fiable (using-plunk.md §4).

## Después: integrar y mantener

- **Enviar desde una web, eventos y workflows, MCP de Plunk:** references/using-plunk.md.
- **Usar Plunk desde claude.ai (MCP remoto con login de GitHub):** references/mcp-remote.md y `assets/mcp-remoto/`. Lee antes la §5: claude.ai no puede mostrar la confirmación de envíos de Plunk.
- **Actualizar, memoria, almacenamiento de imágenes, ntfy, cambiar de dominio, segunda instalación:** references/operations.md.
- **Plunk Lite (desplegar, actualizar o volver a la oficial):** references/plunk-lite.md.
- **Algo falla:** references/troubleshooting.md.

## Lo que más cuesta aprender

Cada punto salió de un error real:

- **El dominio de envío no es el del panel.** Si añades `envio.<dominio>` como dominio de envío, puedes romper el panel: sus registros anulan el comodín del DNS. Usa siempre un subdominio aparte.
- **Los registros de DKIM van con nube gris.** Con la naranja, AWS no puede verificarlos.
- **Cloudflare sí admite nombres DNS de varios niveles** (`plunk.news`). Lo que solo cubre un nivel es su certificado gratuito para webs.
- **Revisa la zona antes de crear registros.** Si la persona tiene varios dominios en la misma cuenta de Cloudflare, es fácil equivocarse de zona.
- **El MX opcional de "inbound email" no se añade.** Sin reglas de recepción en SES, el correo que llega ahí se pierde.
- **Los nombres de las variables los pone la plataforma.** En la plantilla JSON de una web, `{{subject}}` puede no existir y llamarse `{{asunto}}`. Si falta, Plunk responde 422.
- **`/v1/track` suscribe al contacto si no se le dice `"subscribed": false`.**
- **Un dominio de envío solo puede estar en un proyecto de Plunk.** Si lo borras, SES genera tokens DKIM nuevos.
- **Cambiar la IP del servidor rompe los envíos.** La política de IAM está atada a esa IP.
- **SNS reintenta solo 3 veces en un minuto por defecto.** Un despliegue o un reinicio más largo perdía rebotes y quejas, y con ellos las bajas. `ses_setup` sube los reintentos a unos 40 minutos y guarda lo que no llegue en una cola (aws-ses.md §10).
- **La supresión de la cuenta de SES es la red de seguridad.** Bloquea a quien rebotó o se quejó en cualquier envío, también si la dirección vuelve a entrar con una importación. Comprueba que está activa (`ses_check`). Plunk Lite añade su propia lista, que además impide volver a suscribir esas direcciones (references/plunk-lite.md §2).
- **Un envío grande no cabe en el sandbox.** Son 200 emails al día: hay que salir del sandbox antes de la primera campaña de verdad.
