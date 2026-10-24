# Usar Plunk: API, webs, eventos y ajustes

Comprobado contra el código de Plunk 0.17.0. En la API, las rutas van sobre `https://<API_DOMAIN>`.

## Índice
1. Claves
2. Emails transaccionales desde una web (`/v1/send`)
3. Eventos y workflows (`/v1/track`)
4. Seguimiento de aperturas y clics
5. Emails de la plataforma y límite de la API
6. MCP de Plunk
7. Lo que Plunk no hace

## 1. Claves

En el panel: Settings → API Keys, por proyecto.

- **Secreta `sk_…`**: todo (enviar, contactos, campañas). Solo en servidores; nunca en el navegador ni en un formulario público.
- **Pública `pk_…`**: solo registrar eventos (`/v1/track`). Puede ir en una web.

Las cabeceras son `Authorization: Bearer <clave>`.

## 2. Emails transaccionales desde una web (`/v1/send`)

Muchas plataformas (webs de cursos, comunidades, formularios) permiten enviar sus emails de acceso o registro "por llamada HTTP" con una URL, una cabecera de autenticación y una plantilla JSON. Se rellena así:

| Campo | Valor |
|---|---|
| URL (POST, JSON) | `https://<API_DOMAIN>/v1/send` |
| Cabecera (nombre) | `Authorization` |
| Cabecera (valor) | `Bearer sk_…` (clave secreta del proyecto) |

```json
{
  "to": "{{email}}",
  "subject": "{{asunto}}",
  "body": "{{html}}",
  "from": { "name": "Nombre visible", "email": "hola@news.example.com" },
  "reply": "buzon-real@example.com"
}
```

- **Los nombres de las variables (`{{email}}`, `{{asunto}}`, `{{html}}`) son los de la plataforma de la persona, no los de Plunk.** Pide la lista exacta o búscala en su panel: en un caso real la plataforma llamaba `{{asunto}}` al asunto y `{{subject}}` llegaba vacío.
- `subject` y `body` son obligatorios (o un `template` de Plunk). Campos admitidos: `to`, `subject`, `body`, `from`, `reply`, `headers`, `data`, `subscribed`, `template`, `attachments`. Cualquier otro se ignora.
- `from.email` debe estar en un **dominio de envío verificado** (no en la raíz si solo está verificado un subdominio).
- `reply` debe ser un **buzón que exista**: Plunk no recibe correo, y sin `reply` las respuestas irían a la dirección de envío, que normalmente no tiene buzón. Comprueba que el dominio del buzón tiene MX y un servidor que responda.
- El HTML va dentro de una cadena JSON: la plataforma tiene que escapar comillas y saltos de línea al insertar `{{html}}`. Si no lo hace, Plunk responde 400.
- Quien recibe un transaccional queda como contacto **no suscrito** a marketing. Si hay consentimiento explícito para el boletín, añade `"subscribed": true` solo en ese caso.
- En el sandbox de SES solo llega a direcciones verificadas o al simulador (`success@simulator.amazonses.com`).

**Respuestas de Plunk:**

| Código | Significa |
|---|---|
| 200 con `"success": true` | Aceptado (la entrega se ve después en el log como `Delivery confirmed`) |
| 401 | Clave mala, o se usó `pk_` en vez de `sk_` |
| 422 `Request validation failed` | Falta un campo o llega vacío (el detalle dice cuál: p. ej. `subject: String must contain at least 1 character(s)`) |
| 400 | JSON inválido, casi siempre HTML sin escapar |

Si estos emails llevan enlaces de acceso o códigos, pon el tracking en **Marketing only** (sección 4): el seguimiento de clics reescribe los enlaces y los antivirus que los abren automáticamente pueden gastar un enlace de un solo uso antes que la persona.

## 3. Eventos y workflows (`/v1/track`)

Los eventos **no** van en `/v1/send`; son otra llamada:

```
POST https://<API_DOMAIN>/v1/track
Authorization: Bearer pk_…
{"event": "registro", "email": "persona@example.com", "subscribed": false, "data": {"nombre": "Ana"}}
```

- `event` es texto libre: el primer envío lo crea. No hay lista que elegir.
- **`subscribed`: si no se incluye, Plunk suscribe a la persona a marketing.** Para eventos como registro o login sin consentimiento de boletín, envía siempre `"subscribed": false`.
- `data` guarda datos del contacto para usarlos en los emails.
- En el workflow, disparador **Event** con el **mismo nombre exacto** (distingue mayúsculas y espacios). Los workflows también pueden arrancar a mano (API) o por calendario.
- Eventos reservados que genera Plunk (sirven de disparador pero no se pueden enviar con `/v1/track`): `email.sent`, `email.delivery`, `email.open`, `email.click`, `email.bounce`, `email.complaint`, `contact.subscribed`, `contact.unsubscribed`, `segment.<nombre>.entry`, `segment.<nombre>.exit`. Evita automatizar sobre `email.open` por las aperturas falsas.

## 4. Seguimiento de aperturas y clics

Settings → General → **Email tracking** (por proyecto):
- **Enabled**: todo con píxel y enlaces reescritos.
- **Disabled**: nada.
- **Marketing only**: campañas y workflows con seguimiento; los emails de la API (`/v1/send`) sin él. Lo recomendable si la web envía accesos o códigos por Plunk.

El selector solo aparece si existe `SES_CONFIGURATION_SET_NO_TRACKING` en el env (y el configuration set en AWS).

**Aperturas falsas:** Gmail, Apple Mail y algunos antivirus descargan el píxel al recibir el email, y Plunk 0.17 lo cuenta como apertura (llega 1–2 s después de la entrega; las aperturas posteriores sí suelen ser reales). Herramientas como Flodesk o Mailchimp filtran esas aperturas; Plunk aún no (https://github.com/useplunk/plunk/issues/531). Opciones: tomar las aperturas como orientativas y fiarse de los clics, o quitar `OPEN` del configuration set (references/aws-ses.md, sección 9).

**Porcentajes con Marketing only o Disabled:** Plunk 0.17 no tiene en cuenta el modo de seguimiento al calcular aperturas y clics. El dashboard divide entre todos los emails del proyecto (también transaccionales, del simulador, entrantes y no enviados), y Analytics, en la vista de todos los streams, entre todos los enviados. Los transaccionales sin seguimiento bajan el porcentaje: con 1 transaccional y 1 campaña abierta sale 50 % en lugar de 100 %. Está reportado en https://github.com/useplunk/plunk/issues/533. Los datos fiables son la página de cada campaña y Analytics filtrado por stream (pulsa la fila en la tabla "By stream"); la fila Transactional marca 0 % porque no se mide. Avísalo a la persona si usa Marketing only.

## 5. Emails de la plataforma y límite de la API

Al arrancar, Plunk muestra una tabla de funciones. Dos suelen salir desactivadas:

- **Platform emails**: los emails que Plunk envía al usuario del panel. Sin ellos, **"He olvidado mi contraseña" no envía nada** (la página dice que sí), ni llegan avisos de dominio verificado. Para activarlos: `PLUNK_API_KEY` (una clave `sk_` de un proyecto) y `PLUNK_FROM_ADDRESS` (remitente en un dominio verificado, p. ej. `no-reply@news.example.com`). Las añade la persona en Dokploy y redespliega.
- **API rate limiting** (`RATE_LIMIT_ENABLED=true`): límite por proyecto en la API pública. Actívalo cuando una web use la clave `pk_` en un formulario, para acotar altas falsas masivas. Es por proyecto, no por visitante.

Si la persona olvida la contraseña sin Platform emails, se puede restablecer desde el servidor (en la base de datos), pero es más sencillo activarlos desde el principio.

## 6. MCP de Plunk

Hay un MCP oficial, `@plunk/mcp`, que funciona con instalaciones propias: consultar contactos, plantillas, campañas, segmentos y workflows, y también crear, enviar y activar cosas. Por defecto pide confirmación antes de cada envío; `PLUNK_READ_ONLY=true` lo deja en solo lectura.

En Claude Code, que la persona lo añada con su clave (así la clave no pasa por el chat):

```bash
claude mcp add plunk --scope user --env PLUNK_MCP_API_KEY=sk_SU_CLAVE --env PLUNK_MCP_API_URL=https://envio-api.example.com -- npx -y @plunk/mcp
```

Una entrada por instalación (cada una apunta a una API). Para varios proyectos de la misma instalación existen variables `PLUNK_API_KEY_<NOMBRE>`.

Es un MCP **local** (stdio): solo funciona en el ordenador donde se instala y mientras está encendido. Para usarlo desde claude.ai, publícalo en el propio Dokploy con login: references/mcp-remote.md (probado con claude.ai, incluido lo que pasa con las confirmaciones de envío).

## 7. Lo que Plunk no hace

- **No es un buzón.** Solo envía. Para leer y responder correo sigue haciendo falta un servidor de correo o un proveedor (Google Workspace, Zoho, Fastmail, Migadu…). Su "inbound email" convierte correos entrantes en eventos de workflow, no en una bandeja.
- **No reparte credenciales de AWS por proyecto.** Una instalación usa una sola cuenta de SES: facturas y reputación separadas exigen instalaciones separadas.
