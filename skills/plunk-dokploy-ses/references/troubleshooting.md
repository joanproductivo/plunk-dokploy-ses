# Problemas frecuentes

Busca el síntoma; la última columna dice dónde ampliar.

## Despliegue y acceso

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| El contenedor `plunk` tarda en estar healthy | Aplica migraciones de la base de datos al arrancar (el healthcheck da 90 s de margen) | Espera y lee el log; si falla, el error de Prisma/Postgres sale ahí |
| 404 de Traefik en el panel o la API | El dominio en Dokploy apunta a otro servicio o puerto, o se añadió sin redesplegar | Panel y API → servicio `plunk`, puerto 80 (files no va en Dokploy: lo sirve el bucket); HTTPS + Let's Encrypt; despliega de nuevo |
| Bucle de redirecciones con Cloudflare | Modo SSL/TLS "Flexible" | Ponlo en Full o Full (strict) (dns.md §2) |
| Let's Encrypt no emite el certificado | El DNS aún no apunta al servidor, o el proxy interfiere | Comprueba el registro; prueba con nube gris y vuelve a desplegar |
| El panel muestra enlaces a la landing o a las docs de Plunk | Faltan `LANDING_URI`/`WIKI_URI` | Apúntalos al propio panel |
| `AVISO: el parche de arranque no aplica…` en el log | La versión nueva cambió el script de arranque | Funciona, pero arranca todo; revisa operations.md §3 |
| Un cambio de variable no tiene efecto | No está en la sección `environment` del compose, o se reinició en vez de desplegar | Añádela al compose y pulsa Deploy |
| Tras guardar el env por la API, SES deja de funcionar | Se sobrescribieron las claves de AWS con los valores ocultos | La persona vuelve a pegarlas en Dokploy y despliega; no escribas el env por la API después de pegar claves |
| El MCP de Dokploy no ve el proyecto | La clave de API es de otra organización de Dokploy | Clave creada en la organización correcta y reiniciar el MCP |
| Leer logs con filtro de búsqueda devuelve error 500 | Fallo intermitente del filtro `search` del MCP de Dokploy | Lee sin filtro, o reintenta |

## AWS SES

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| No aparece `AWS SES quota: …` en el log; errores `InvalidClientTokenId` | Claves aún de ejemplo o mal pegadas | La persona revisa `AWS_SES_ACCESS_KEY_ID`/`SECRET` y despliega |
| `AccessDenied` en SES con claves correctas | Cambió la IP pública del servidor, o la región no coincide | Ejecuta `ses_setup` con la IP nueva; misma región en env y AWS |
| Plunk no marca entregas, aperturas ni rebotes | Suscripción SNS sin confirmar o eventos sin configurar | `ses_check`; aws-ses.md §1 "Orden" |
| En el sandbox no llega el email | El destinatario no está verificado en SES | Envía al simulador o verifica la dirección (aws-ses.md §5) |
| La dirección verificada sigue en `PENDING` | No se pulsó el enlace de AWS, o caducó (24 h) | Mira Spam y Promociones; si caducó, borra la identidad y créala otra vez (aws-ses.md §5) |
| Tras salir del sandbox sigue enviando a 1/s | Plunk lee la cuota solo al arrancar | Reinicia el contenedor `plunk` |
| No se puede cambiar el plan de precios de SES | Hay una petición de producción en revisión | Espera la respuesta de AWS |
| AWS deniega la producción | Falta contexto de cómo se obtienen los contactos, o la web no muestra formulario | Responder en el mismo caso (aws-ses.md §6), sin reenviar la petición |
| DKIM `PENDING` o `FAILED` | Registros DNS mal o en otra zona | `check_dns.sh` y dns.md §4 |

## Uso

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| 401 en `/v1/send` | Clave pública o equivocada | Usa la `sk_` del proyecto |
| 422 `Request validation failed` | Un campo llega vacío; a menudo la variable de la plataforma tiene otro nombre (`{{asunto}}` en vez de `{{subject}}`) | Lee el detalle de la respuesta y la lista de variables de la plataforma |
| 400 en `/v1/send` | HTML sin escapar dentro del JSON | Que la plataforma escape `{{html}}` |
| Rechazo del remitente | `from` fuera de un dominio verificado | Usa una dirección del dominio de envío |
| 413 en `/v1/send` o en el panel | Petición de más de 10 MB (nginx) o, con Plunk Lite, de más de 2 MB fuera de `/v1/send` | Adjuntos de unos 7 MB como mucho; las imágenes, subidas al editor y no pegadas en base64 |
| 503 «Too many large sends in progress» (Plunk Lite) | Más de 8 envíos grandes (más de 2 MB) a la vez | Reintenta tras el `Retry-After`; repártelos en el tiempo |
| 429 «Too many login attempts» (Plunk Lite) | 10 intentos fallidos con ese email en 15 minutos | Espera 15 minutos; un login correcto pone la cuenta a cero |
| 429 en `/v1/track`, `/v1/send` o contactos | Límite de peticiones por proyecto (`RATE_LIMIT_ENABLED`, activado en la plantilla) | Respeta `Retry-After`. Si una integración propia lo necesita de verdad, sube `RATE_LIMIT_*_PER_SECOND` en el env |
| Emails marcados como abiertos sin abrir | Precarga del píxel por Gmail/Apple/antivirus | using-plunk.md §4 |
| Enlaces de acceso que "ya se usaron" | El seguimiento de clics y los antivirus los abren antes | Tracking en "Marketing only" |
| El dashboard marca un porcentaje de aperturas o clics más bajo que las campañas | Con tracking "Marketing only" o "Disabled", Plunk 0.17 cuenta en el total los emails sin seguimiento (useplunk/plunk#533) | Mira la página de la campaña o Analytics filtrado por stream (using-plunk.md §4) |
| Altas de eventos suscriben a gente sin consentimiento | `/v1/track` sin `"subscribed": false` | Añádelo |
| 403 «Public keys are switched off» en `/v1/track` (Plunk Lite) | `PLUNK_LITE_PUBLIC_TRACK=off` y la llamada usa la `pk_` | Llámalo desde el servidor con la `sk_`, o vuelve a poner `on` |
| 403 al usar `segments` en `/v1/track` (Plunk Lite) | Los segmentos solo se admiten con la `sk_` | Llama desde el servidor con la `sk_` |
| 422 «Some segments cannot take contacts» (Plunk Lite) | Un id de `segments` no existe, es de otro proyecto o es un segmento con filtros | Usa ids de segmentos estáticos del proyecto |
| 400 «Not enough SES quota» al enviar una campaña (Plunk Lite) | No cabe en el 95 % de la cuota de SES de 24 horas, contando lo enviado y lo que les falta a las campañas en curso | Envíala o prográmala cuando haya cuota, o pide más a AWS |
| «Could not read the account's status» en el log (Plunk Lite) | La política de IAM no tiene `ses:GetAccount` | Ejecuta `ses_setup` otra vez (aws-ses.md §1). Mientras tanto, la pausa se deduce solo de los rechazos |
| Aviso «Amazon SES» en el banner y los emails parados (Plunk Lite) | SES dio la cuota diaria por agotada o pausó la cuenta: la cola espera (15 min) o se pausa y prueba cada 30 min | Mira la cuenta en SES (aws-ses.md). El aviso se cierra solo con el primer email que sale |
| El workflow no se dispara | El nombre del evento no coincide exactamente | Mismo texto, mayúsculas y espacios incluidos |
| No aparece el selector "Email tracking" | Falta `SES_CONFIGURATION_SET_NO_TRACKING` | Defínela y despliega |
| "He olvidado mi contraseña" no envía nada | Platform emails desactivados | `PLUNK_API_KEY` + `PLUNK_FROM_ADDRESS` (using-plunk.md §5) |
| Las respuestas a los emails se pierden | `reply` apunta a un dominio sin buzón o sin servidor de correo activo | Usa un buzón real; comprueba su MX |
| `[WEBHOOK] Unknown event type: Send` en el log | El configuration set publica SEND (montado con una versión anterior de esta skill) y Plunk 0.17 no lo usa | Inofensivo, pero duplica las llamadas al webhook: quita SEND con `sesv2:UpdateConfigurationSetEventDestination` (mismo `SnsDestination`, `Enabled: true`) en los dos sets |

## MCP remoto (claude.ai)

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| "No se pudo registrar con el servicio de inicio de sesión" al conectar | Cloudflare bloquea `/.idp/` y `/.auth/` (regla WAF contra rutas con `/.`) | mcp-remote.md §7 |
| Envío a varios, campaña o activar workflow falla con `-32021` | claude.ai no admite la confirmación de Plunk | mcp-remote.md §5 |
