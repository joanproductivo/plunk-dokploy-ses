# AWS SES para Plunk

## Índice
1. Qué se crea y por qué
2. Ejecutar la configuración
3. Las access keys (las crea la persona)
4. Comprobar el estado
5. Sandbox y pruebas
6. Salir del sandbox (producción)
7. Plan de precios de SES
8. Después de cambios en la cuenta
9. Quitar el seguimiento de aperturas
10. Que no se pierdan rebotes ni quejas
11. Dominio de seguimiento propio

## 1. Qué se crea y por qué

`scripts/ses_setup.snippet.py` crea esto en la región elegida (idempotente):

| Recurso | Nombre | Para qué |
|---|---|---|
| Usuario IAM | `plunk-ses` (sin access key) | Identidad con la que Plunk llama a SES |
| Política inline | `plunk-ses-sending` | Solo las 8 acciones que usa Plunk, solo en esa región y **solo desde la IP del servidor** |
| Topic SNS | `plunk-ses-events` (SignatureVersion 2) | SES publica ahí lo que pasa con cada email |
| Política del topic | | Solo SES de esta cuenta puede publicar |
| Configuration set | `plunk-configuration-set` | Eventos DELIVERY, OPEN, CLICK, BOUNCE, COMPLAINT → SNS (sin SEND: Plunk no lo usa) |
| Configuration set | `plunk-no-tracking-configuration-set` | Igual, sin OPEN ni CLICK |
| Suscripción HTTPS | `https://<API_DOMAIN>/webhooks/sns` | Plunk recibe los eventos y la confirma solo |
| Reintentos de la suscripción | 40, de 10 a 100 s (~40 min) | Que un despliegue o un reinicio no pierda rebotes ni quejas (§10) |
| Cola SQS | `plunk-ses-events-dlq` (14 días) | Lo que SNS no consiga entregar queda guardado en vez de perderse (§10) |
| Supresión de la cuenta | BOUNCE y COMPLAINT | SES no vuelve a intentar direcciones que rebotaron o se quejaron (§10) |

Las 10 acciones: `ses:SendRawEmail`, `ses:GetSendQuota`, `ses:VerifyDomainDkim`, `ses:GetIdentityDkimAttributes`, `ses:GetIdentityVerificationAttributes`, `ses:SetIdentityMailFromDomain`, `ses:SetIdentityFeedbackForwardingEnabled`, `ses:DeleteIdentity`, `ses:DescribeConfigurationSet` y `ses:GetAccount`. Plunk crea y borra las identidades de dominio él mismo cuando se añaden o quitan en su panel; por eso necesita las de identidad, además de enviar. `ses:DescribeConfigurationSet` la usa al arrancar para comprobar que los configuration sets tienen su destino de eventos; sin ella, el log dice «Skipped configuration set check». `ses:GetAccount` (de la API v2 de SES) la usa Plunk Lite para leer el estado de la cuenta cuando un envío se rechaza: si SES la ha pausado, pausa la cola al primer rechazo. Sin ella, el log dice «Could not read the account's status» y la pausa se deduce solo de los rechazos. `GetAccountSendingEnabled` no sirve para esto: no cambia cuando SES pausa la cuenta. En una instalación que ya existía, ejecuta `ses_setup` otra vez (actualiza la política y los tipos de evento) y reinicia Plunk, que solo hace la comprobación de los configuration sets al arrancar. `ses_check` muestra lo que falta en `iam.missing_actions`.

Además, un segundo statement, `PlunkDLQ`, con las mismas condiciones y solo sobre la cola `plunk-ses-events-dlq`: `sqs:ReceiveMessage`, `sqs:DeleteMessage`, `sqs:ChangeMessageVisibility` y `sqs:GetQueueAttributes`. Plunk Lite lo usa para vaciar la DLQ él solo (§10). Va aparte porque el de SES lleva `Resource: "*"`: con las acciones de SQS ahí, valdrían para todas las colas de la cuenta. Sin él, el panel avisa «AWS dead-letter queue not readable». `ses_setup` escribe la política entera (`PutUserPolicy`): lo que alguien haya añadido a mano a `plunk-ses-sending` desaparece al volver a ejecutarlo, así que cualquier permiso más va en el snippet.

**Por qué la condición de IP:** si las claves se filtran, no sirven desde ningún otro sitio. La contrapartida: si el servidor cambia de IP pública, los envíos fallan con AccessDenied hasta actualizar la política (vuelve a ejecutar el snippet con la IP nueva).

**Por qué dos configuration sets:** el que lleva OPEN hace que SES inserte el píxel invisible; el que lleva CLICK reescribe los enlaces. El segundo set, sin ambos, es lo que permite a Plunk ofrecer el selector "Email tracking" (Enabled / Disabled / Marketing only). Plunk solo muestra ese selector si la variable `SES_CONFIGURATION_SET_NO_TRACKING` existe.

**Orden:** la API de Plunk debe responder ya por HTTPS antes de crear la suscripción, porque SNS manda el mensaje de confirmación en el momento. Si la suscripción queda en `PendingConfirmation`, comprueba que `https://<API_DOMAIN>/health` da 200, bórrala y vuelve a ejecutar el snippet.

## 2. Ejecutar la configuración

Datos que necesitas: región, ID de la cuenta de AWS (12 dígitos), IP pública del servidor (en Dokploy: Settings → Server, o `settings-getIp` del MCP), dominio de la API.

- **Con el MCP oficial de AWS** (`aws-mcp`, herramienta `run_script`): copia el snippet, sustituye `__REGION__`, `__ACCOUNT_ID__`, `__SERVER_IP__` y `__API_DOMAIN__`, y pásalo como `code` (con `aws_profile` si hay varios perfiles). El script comprueba que la cuenta es la esperada antes de tocar nada.
- **Con un perfil del AWS CLI:**
  ```bash
  python3 scripts/run_snippet.py scripts/ses_setup.snippet.py --profile PERFIL --set REGION=eu-north-1 --set ACCOUNT_ID=123456789012 --set SERVER_IP=203.0.113.10 --set API_DOMAIN=envio-api.example.com
  ```
- **Sin acceso programático:** créalo en la consola siguiendo la tabla de arriba (IAM → Users; SNS → Topics; SES → Configuration sets → Event destinations). Es más lento pero equivalente.

Si la cuenta es de las nuevas cuentas de AWS con experiencia gestionada (proyectos de AWS Settings), todo esto funciona igual; los recursos deben ir en la región asignada al proyecto.

## 3. Las access keys (las crea la persona)

Una access key es un secreto: no debe pasar por el chat ni por las herramientas. Dale estos pasos:

1. Consola de AWS → IAM → Users → `plunk-ses` → pestaña **Security credentials** → **Create access key**.
2. Caso de uso: **Application running outside AWS** → Next → Create.
3. En Dokploy, en el compose de Plunk → pestaña **Environment**: pega el Access key ID en `AWS_SES_ACCESS_KEY_ID` y el Secret en `AWS_SES_SECRET_ACCESS_KEY` (sustituyendo `PEGAR_EN_DOKPLOY`), guarda y pulsa **Deploy**.

**Desde ese momento no vuelvas a escribir el env por la API de Dokploy** (`compose-saveEnvironment` o equivalente): Dokploy devuelve el env con los secretos ocultos y, al guardarlo, sustituirías las claves reales. Cualquier cambio de variables lo hace la persona en la interfaz.

**Verificación:** en el log del contenedor `plunk` debe salir una línea como `AWS SES quota: 1 emails/second (0/200 emails sent today)`. Si sale, las claves funcionan desde el servidor.

## 4. Comprobar el estado

`scripts/ses_check.snippet.py` es de solo lectura (mismos dos modos de ejecución, con `REGION` y `ACCOUNT_ID`). Qué mirar:

| Campo | Bien | Si no |
|---|---|---|
| `identities.<dominio>.dkim` | `SUCCESS` | `PENDING`: DNS aún no visible o SES no ha recomprobado (puede tardar horas); `FAILED`: registros mal, ver references/dns.md |
| `identities.<dominio>.mail_from_status` | `SUCCESS` | Revisa MX y TXT de `plunk.<dominio>` |
| `sns_subscriptions[].confirmed` | `true` | Ver "Orden" en la sección 1 |
| `sns_subscriptions[].retries` | `40` | `3` es el valor por defecto: ejecuta `ses_setup` otra vez con la suscripción ya confirmada (§10) |
| `sns_subscriptions[].dlq` | la ARN de `plunk-ses-events-dlq` | Igual que la fila anterior |
| `ses.suppressed_reasons` | `["BOUNCE", "COMPLAINT"]` | Ejecuta `ses_setup` otra vez (§10) |
| `iam.missing_actions` | `[]` | Ejecuta `ses_setup` otra vez y reinicia Plunk |
| `iam.missing_dlq_actions` | `[]` | Con Plunk Lite: ejecuta `ses_setup` otra vez, antes de desplegar una imagen que vacía la DLQ |
| `iam.dlq_statement_ok` | `true` | El statement `PlunkDLQ` apunta a otra cola o región, o no lleva las condiciones de IP y región: ejecuta `ses_setup` otra vez |
| `alarms` | las tres en `OK` | Ejecuta `ses_alarms` (antes de enviar en volumen) |
| `config_sets` | los dos, con `plunk-sns` habilitado | Ejecuta `ses_setup` otra vez |
| `iam.access_keys` | una, `Active` | Ninguna: falta el paso 3. Dos: que la persona borre la que no usa |
| `iam.allowed_ip` | IP actual del servidor | Ejecuta `ses_setup` con la IP nueva |
| `ses.production` | `true` tras salir del sandbox | Sección 6 |
| `ses.pricing_plan` | `NONE` (à la carte) o `ESSENTIALS` | Sección 7 |

`dkim_tokens` son los que pide `scripts/check_dns.sh`.

## 5. Sandbox y pruebas

Las cuentas nuevas empiezan en el sandbox: 200 emails al día, 1 por segundo y **solo a destinatarios verificados en SES** (en esa cuenta y región). El `from` sigue siendo el dominio de envío; lo que limita el sandbox es a quién se envía.

**Simulador de SES (sin verificar nada).** Prueba toda la cadena SES → SNS → Plunk, rebotes y quejas incluidos. Envía un email a cada dirección (`plunk_send_email`, una por llamada, o `/v1/send`) desde una dirección del dominio de envío, y mira el log de `plunk`:

| Dirección | Qué simula SES | Qué debe salir en el log |
|---|---|---|
| `success@simulator.amazonses.com` | Entrega | `[WEBHOOK] Delivery confirmed for …` |
| `bounce@simulator.amazonses.com` | Rebote permanente | `[WEBHOOK] Permanent bounce received for …` |
| `complaint@simulator.amazonses.com` | Entrega y queja de spam | `[WEBHOOK] Complaint received for …` y también `Delivery confirmed` |
| `suppressionlist@simulator.amazonses.com` | Dirección en la lista de supresión | `[WEBHOOK] Permanent bounce received for …` |

Cada evento termina en `Processed <tipo> event for email <id>` y `POST /webhooks/sns → 200`. Los envíos al simulador no cuentan en la cuota ni en la reputación de SES, y Plunk los excluye de sus tasas de rebote y queja. Al interpretar el resultado:
- Los envíos transaccionales crean el contacto con `subscribed: false`, así que esa casilla no demuestra que el rebote lo diera de baja. Lo que lo demuestra es que el `updatedAt` del contacto (`plunk_get_contact`) coincide con la hora del evento.
- En la queja, la entrega puede llegar después: el email puede verse como entregado en la actividad aunque el contacto quedó tratado.
- Los cuatro contactos del simulador se quedan en el proyecto. Avisa a la persona; si quiere, los borra ella desde el panel.

**Un buzón real (dirección verificada).** Para ver el email en una bandeja (formato, carpeta, autenticación), verifica la dirección de destino en la misma cuenta y región:

1. Pide permiso antes: AWS manda un email a esa dirección. Usa solo direcciones de la persona o de alguien que lo haya pedido.
2. `sesv2:CreateEmailIdentity` con `EmailIdentity: "<dirección>"` (o consola: SES → Identities → Create identity → Email address). Queda en `PENDING`.
3. La persona pulsa el enlace del email "Amazon Web Services – Email Address Verification Request in region …" (puede caer en Spam o Promociones). **Caduca a las 24 h**: si caduca, borra la identidad (`sesv2:DeleteEmailIdentity`) y créala otra vez para que llegue otro.
4. `sesv2:GetEmailIdentity` debe dar `VerificationStatus: SUCCESS`. Desde ese momento se puede enviar a esa dirección.
5. Envía la prueba y pide a la persona que abra "Mostrar original" (Gmail) y compruebe SPF, DKIM y DMARC en PASS.

Ten en cuenta:
- **La prueba de campaña de Plunk** (`plunk_test_campaign` o el botón del editor) va al email de la cuenta del panel: en el sandbox, esa dirección también tiene que estar verificada.
- **No envíes a direcciones del propio dominio de envío** porque esté verificado. SES lo permite, pero un subdominio de envío normalmente no tiene MX: el email rebota y resta reputación justo antes de pedir producción. Compruébalo con `dig +short MX <dominio>`.
- La dirección verificada sirve solo como destinatario de prueba. Plunk exige que el `from` sea de un dominio verificado en su panel.
- Las identidades de email no estorban al salir del sandbox; se pueden dejar.

## 6. Salir del sandbox (producción)

Es una petición a AWS en nombre de la persona: hazla solo con su permiso explícito y con los datos que ella confirme.

**Antes de pedirlo:**
- Todos los dominios de envío en `SUCCESS` (DKIM y MAIL FROM). AWS revisa la configuración.
- DMARC publicado en el dominio.
- La web que se indique debe mostrar **un formulario de suscripción visible** con enlace a la política de privacidad: AWS puede visitarla. Sin eso es probable que lo deniegue.
- Comprueba que no hay ya una revisión abierta (`ses.review` en ses_check).

**La petición** (API `sesv2:PutAccountDetails`): `ProductionAccessEnabled: true`, `MailType` (`MARKETING` si hay boletines, aunque también haya transaccionales; `TRANSACTIONAL` si solo hay transaccionales), `WebsiteURL`, `ContactLanguage` (`EN` o `JA`). Por consola: SES → Account dashboard → Request production access.

**Respuestas posibles** (en `ses.review.Status`): `GRANTED` (suele dar 50.000/día y 14/s en la primera concesión), `DENIED`, o un correo automático de AWS pidiendo más información.

**Si AWS pide información o lo deniega:** no vuelvas a enviar la petición (AWS la rechaza porque ya hay una decisión). La persona responde **en el mismo caso** de Support Center (consola → Support → Your support cases); leer casos por API requiere un plan de soporte de pago. Respuesta modelo para que la adapte (en inglés, sin inventar nada que no sea cierto):

> Hello, thank you for the review. Here is the requested information:
>
> **1. Website:** https://example.com, [what the site is about].
>
> **2. Email type:** mainly marketing ([frequency] newsletter with [content]), plus transactional emails triggered by the user: [sign-up confirmation (double opt-in), welcome, login links…].
>
> **3. Volume:** about [X] subscribers; approximately [Y] emails per month.
>
> **4. Recipient source:** only people who subscribe themselves through [the form at https://example.com/subscribe], with a link to our privacy policy. [New subscribers confirm via double opt-in.] We never buy, rent or scrape email lists.
>
> **5. Bounce and complaint handling:** we send through Plunk, a self-hosted email platform. Our SES configuration sets publish Delivery, Bounce, Complaint, Open and Click events to an SNS topic subscribed to Plunk, which automatically suppresses addresses that bounce or complain, so they are never emailed again. Every marketing email includes a visible unsubscribe link and RFC 8058 one-click List-Unsubscribe headers, and unsubscribes take effect immediately. We monitor bounce and complaint rates in Plunk's dashboard.
>
> **6. Sample email:** Subject: "[subject]". Body: [short description of a typical email], and a footer with the sender's details and an unsubscribe link.
>
> Our sending domain [news.example.com] is verified in [region] with Easy DKIM and a custom MAIL FROM domain, and [example.com] publishes DMARC.
>
> Thank you.

Los puntos 5 y el último párrafo describen lo que esta skill configura, así que se pueden dejar tal cual si la instalación se hizo con ella. Lo de los corchetes lo rellena la persona con datos reales.

**Si es la primera petición y no se lleva lista**, la experiencia es que AWS deniega con más facilidad las cuentas sin historial; una web con formulario visible y una explicación clara del origen de los contactos marcan la diferencia.

## 7. Plan de precios de SES

Desde julio de 2026 AWS asigna a las cuentas nuevas de SES el plan **Essentials** automáticamente.

| | À la carte (`NONE`) | Essentials |
|---|---|---|
| Por 1.000 emails | 0,10 $ | 0,16 $ |
| Incluye | solo envío | envío + analíticas de entregabilidad de AWS (Virtual Deliverability Manager) |

Plunk ya muestra aperturas, clics, rebotes y quejas, así que para la mayoría à la carte sale más barato. Cambiarlo es un cambio de facturación: pregunta antes. Se hace con `sesv2:PutAccountPricingAttributes` (`Plan: NONE`) o en la consola de SES. Como el plan lo asignó AWS, el primer cambio se aplica al momento. **No se puede cambiar mientras haya una petición de producción en revisión**: en ese caso, espera a la respuesta.

Si la cuenta está en el plan gratuito de AWS (cuentas nuevas con crédito), avisa de que hay que pasarla a plan de pago antes de que caduque, o AWS cierra la cuenta y SES deja de enviar.

## 8. Después de cambios en la cuenta

**Plunk lee la cuota de SES solo al arrancar.** Tras salir del sandbox (o tras un aumento de cuota), reinicia el contenedor `plunk` (reiniciar no toca el env). En el log debe aparecer la cuota nueva, p. ej. `AWS SES quota: 14 emails/second (0/50000 emails sent today)`. Si no lo reinicias, sigue enviando al ritmo del sandbox.

Plunk usa la cuota que lee de SES. Antes de enviar en volumen, conviene fijar `EMAIL_RATE_LIMIT_PER_SECOND` un poco por debajo (§10).

## 9. Quitar el seguimiento de aperturas

Gmail (proxy de imágenes), Apple Mail Privacy Protection y algunos antivirus descargan el píxel al recibir el email, y Plunk 0.17 cuenta eso como apertura (en las pruebas llegó 1–2 s después de la entrega). Está reportado en https://github.com/useplunk/plunk/issues/531. Si la persona prefiere no ver aperturas falsas, quita `OPEN` del configuration set principal y se queda con los clics, que sí son fiables:

`sesv2:UpdateConfigurationSetEventDestination` en `plunk-configuration-set` / `plunk-sns` con `MatchingEventTypes: ["DELIVERY","CLICK","BOUNCE","COMPLAINT","REJECT"]` (mantén `Enabled: true` y el mismo `SnsDestination`). Es reversible volviendo a añadir `OPEN`. Pide confirmación antes: cambia lo que mide la herramienta.

## 10. Que no se pierdan rebotes ni quejas

Las cuentas de SES se pueden suspender por una tasa de rebotes o de quejas alta, y Plunk solo da de baja a quien rebota o se queja si le llega el aviso. Tres ajustes, todos en `ses_setup`, cubren los huecos:

- **Reintentos de SNS.** Por defecto, SNS reintenta un webhook HTTPS solo 3 veces en unos 60 s. Un despliegue o un reinicio de Plunk que tarde más pierde para siempre los rebotes y quejas de ese rato. La política de `ses_setup` sube a 40 reintentos, unos 40 minutos.
- **Cola de mensajes no entregados (DLQ).** Si aun así SNS no consigue entregar un evento, lo deja 14 días en `plunk-ses-events-dlq` en lugar de tirarlo. Se ve en la consola de SQS.
- **Supresión de la cuenta.** Con BOUNCE y COMPLAINT, SES no vuelve a intentar una dirección que rebotó o se quejó, aunque Plunk le mande un email (por ejemplo, tras reimportar una lista vieja): responde con un rebote `OnAccountSuppressionList` que no cuenta en la tasa de AWS. Suele venir activa en las cuentas nuevas. Si alguien la desactiva, esas direcciones vuelven a recibir.

**Vaciar la DLQ:** Plunk Lite la vacía solo (se prueba con `scripts/dlq_test.snippet.py`, plunk-lite.md §4). Comprueba cada 15 minutos si tiene mensajes, y la vacía también cuando salta la alarma `ses-eventos-dlq` o se pulsa «Process AWS dead-letter queue now» en Settings → Alerts. Cada mensaje pasa por el mismo webhook, con su firma y su cuenta comprobadas. Los rebotes y las quejas se procesan siempre, porque Plunk no los registra dos veces. Las entregas, aperturas y clics, solo si tienen menos de 24 h: pasado ese tiempo la cola de eventos ya no recuerda el mensaje, y se volverían a lanzar sus workflows y a sumar a los contadores, así que se descartan. Lo que el webhook no puede procesar por un fallo pasajero (la base de datos, Redis o AWS caídos) vuelve a la cola, cada vez más tarde, y nunca se borra mientras sigan caídos. Solo se descarta, con su contenido en el log, un mensaje con la firma rechazada en 4 lecturas y más de una hora, o uno que falla en 8 lecturas y más de un día con todo lo demás funcionando. En la actividad del contacto, el rebote o la queja recuperados salen marcados «Recovered from the AWS dead-letter queue». Con la imagen oficial de Plunk no hay nada de esto: hay que reenviar a mano al webhook, y las entregas, aperturas y clics ni siquiera dentro de las 24 h.

La suscripción tiene que estar confirmada para poner los reintentos y la DLQ: si `ses_setup` dice que aún no lo está, vuelve a ejecutarlo cuando `ses_check` la dé por confirmada.

**Antes de enviar en volumen** (miles de emails), comprueba también:
- **`EMAIL_RATE_LIMIT_PER_SECOND` un poco por debajo de la cuota.** Por ejemplo, `12` con 14/s, para no rozar el límite de SES.
- **`AUTO_PROJECT_DISABLE=true`.** Con Plunk Lite, una campaña que rebota (≥100 enviados, ≥5 % de rebotes o ≥0,1 % de quejas) se cancela sola y un workflow igual se desactiva; el proyecto entero solo se desactiva como último recurso, con `PLUNK_LITE_DISABLE_BOUNCE_PERCENT` (`8`) y `PLUNK_LITE_DISABLE_COMPLAINT_PERCENT` (`0.4`, con punto) en 7 días, antes de que AWS pause la cuenta (10 % y 0,5 %). Se reactiva desde el panel. Con la imagen oficial, el crítico desactiva el proyecto directamente.
- **Valores de entorno con punto decimal** (`0.4`, no `0,4`). Plunk Lite acepta la coma desde `sha-5a1ebe2`, pero una imagen anterior no arrancaba con ella.
- **Si la cuenta de AWS está en el plan gratuito** (FREE), caduca a los 6 meses o al agotar el crédito, y con ella SES. Pásala a un plan de pago antes (AWS Settings → Billing), con un límite de gasto si se quiere.
- **Alarmas de CloudWatch (recomendado), con `scripts/ses_alarms.snippet.py`** (`ALARM_EMAIL`, `API_DOMAIN`, `PANEL=si` con Plunk Lite). Un topic SNS `plunk-alarmas` con una suscripción de email y tres alarmas: `AWS/SES Reputation.BounceRate` ≥ 0,04 y `Reputation.ComplaintRate` ≥ 0,0008 (sin dimensiones, `Maximum`, 1 h, `TreatMissingData=ignore`: SES publica esas métricas a intervalos irregulares) y `AWS/SQS ApproximateNumberOfMessagesVisible` de `plunk-ses-events-dlq` ≥ 1 (5 min, `notBreaching`). Caben en la capa gratuita. Con Plunk Lite, suscribe además el topic por HTTPS a `<API>/webhooks/sns` (con los mismos reintentos que los eventos y **sin** DLQ) y las alarmas salen también en el banner del panel.
- **Que la cuenta ya salió del sandbox.** En el sandbox el límite es de 200 emails al día.

## 11. Dominio de seguimiento propio

Por defecto, en los emails con seguimiento SES reescribe los enlaces y el píxel de apertura con su dominio compartido (`r.<región>.awstrack.me`). Con un subdominio propio, los enlaces coinciden con la marca y no dependen de ese dominio. Se hace en AWS y en el DNS: no se añade en el panel de Plunk ni en Dokploy, y no pasa por el servidor (destinatario → Cloudflare → AWS → destino del enlace), así que Traefik no interviene.

Es **una por configuration set**: todos los emails con seguimiento de la instalación usan el mismo subdominio, aunque salgan desde varios dominios. Solo se configura en `plunk-configuration-set`; `plunk-no-tracking-configuration-set` no reescribe enlaces.

Conviene hacerlo antes del primer envío grande. Pasos, con Cloudflare y `example.com` como ejemplo:

1. **Elige el subdominio.** `click.example.com`, de **un solo nivel**: el certificado gratuito de Cloudflare no cubre `click.news.example.com` y el HTTPS fallaría.
2. **Crea el registro** en la zona `example.com`: CNAME `click` → `r.<región>.awstrack.me`, con **nube naranja** (es lo que da el HTTPS). El modo SSL/TLS debe ser Full o Full (strict), no Flexible.
3. **Comprueba el HTTPS:** `curl --head https://click.example.com/favicon.ico` tiene que dar `200`, `x-amz-ses-region: <región>` y `x-amz-ses-request-protocol: https`. Si no, para aquí.
4. **Verifica el dominio en SES.** Si `example.com` ya es una identidad verificada en esa cuenta, sáltate este paso. Si solo lo está `news.example.com`, no basta: crea la identidad del subdominio, sin añadir el dominio principal al panel de Plunk, para que el proyecto no pueda enviar desde él.
   - `sesv2:CreateEmailIdentity` con `EmailIdentity: click.example.com`.
   - Añade los 3 CNAME de DKIM que devuelve, con **nube gris**: `<token>._domainkey.click` → `<token>.dkim.amazonses.com`.
   - Espera a que `sesv2:GetEmailIdentity` dé `DkimAttributes.Status: SUCCESS`. En la instalación de referencia tardó unos 10 minutos.
5. **Asígnalo, con la confirmación de la persona.** Hazlo solo con los pasos 3 y 4 bien hechos: desde ese momento todos los emails con seguimiento usan este dominio, y si no funciona sus enlaces se rompen. Los emails ya enviados no cambian.
   ```bash
   aws sesv2 put-configuration-set-tracking-options --configuration-set-name plunk-configuration-set --custom-redirect-domain click.example.com --https-policy REQUIRE --region <región>
   ```
6. **Prueba con una campaña, no con `/v1/send`.** Con «Email tracking» en «Marketing only», un envío transaccional sale sin seguimiento y su enlace va directo, sin probar nada. Crea una campaña filtrada a una sola dirección (`email` `equals`) y comprueba `totalRecipients: 1` antes de enviarla. El enlace del email debe empezar por `https://click.example.com/`, abrir su destino y sumar en `clickedCount` de la campaña. En el sandbox, la dirección tiene que estar verificada.

**Si el proxy no da HTTPS:** la vía que documenta AWS es CloudFront, con `r.<región>.awstrack.me` como origen y la cabecera `Host` de quien pide reenviada al origen. Su certificado de ACM tiene que estar en `us-east-1`; comprueba antes que la cuenta lo permite.

**Quitarlo:** repite el comando del paso 5 sin `--custom-redirect-domain`. Mantén el CNAME mientras queden emails enviados con ese dominio, o sus enlaces dejarán de funcionar.
