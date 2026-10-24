# MCP de Plunk accesible desde claude.ai

Para usar Plunk desde claude.ai (o cualquier cliente MCP remoto) sin tener un ordenador encendido. Probado en octubre de 2026 con @plunk/mcp 0.17.0, claude.ai y Claude Code.

## Índice
1. Por qué hace falta montarlo
2. Cómo está hecho
3. Instalación
4. Conectar en claude.ai
5. Confirmación de envíos (importante)
6. Comprobar y probar
7. Problemas conocidos
8. Mantenimiento

## 1. Por qué hace falta montarlo

El MCP oficial de Plunk (`@plunk/mcp`) es **local** (stdio): solo funciona en el ordenador donde se instala. claude.ai necesita una dirección HTTPS con login. Publicarlo sin login sería entregar a cualquiera que adivine la URL el poder de enviar emails en nombre de la persona.

## 2. Cómo está hecho

Un compose aparte en Dokploy (`assets/mcp-remoto/docker-compose.yml`), con dos servicios:

| Servicio | Qué hace | Expuesto |
|---|---|---|
| `plunk-mcp` | Imagen construida en el propio despliegue (`dockerfile_inline`): Node 22 + `@plunk/mcp` + un pequeño servidor HTTP (`server.mjs`) que sirve el MCP por Streamable HTTP | No: solo en la red interna del compose |
| `plunk-mcp-auth` | [mcp-auth-proxy](https://github.com/sigbit/mcp-auth-proxy): servidor OAuth 2.1 con registro dinámico (DCR) para claude.ai; exige login con GitHub y solo deja pasar a los usuarios permitidos | Sí: dominio `envio-mcp.<dominio>` → puerto 80 |

`server.mjs` atiende los dos protocolos: el nuevo (2026-07-28, el que usa claude.ai) y el de 2025, este último con sesiones con estado para que el servidor pueda pedir confirmación al usuario. Para cambiarlo, edita `server.mjs` y regenera el compose con `python3 gen_compose.py` (dentro de `server.mjs` no puede haber `$`: Compose lo tomaría por una variable).

## 3. Instalación

1. **Compose:** crea en Dokploy un compose raw `plunk-mcp` (en el mismo proyecto que Plunk), pega `assets/mcp-remoto/docker-compose.yml` y activa isolatedDeployment.
2. **Env:** usa `assets/mcp-remoto/env.template`. Puedes guardarlo por la API mientras solo tenga los `PEGAR_EN_DOKPLOY`; después, lo edita la persona.
3. **Dominio:** `envio-mcp.<dominio>` → servicio `plunk-mcp-auth`, puerto 80, HTTPS con Let's Encrypt.
4. **Primer despliegue sin claves.** Sirve para comprobar que el servidor construye la imagen y que el dominio responde. Sin claves nadie puede entrar.
5. **Lo que hace la persona:**
   - **App OAuth de GitHub** en https://github.com/settings/applications/new:
     - Homepage `https://envio-mcp.<dominio>`;
     - callback `https://envio-mcp.<dominio>/.auth/github/callback`;
     - después, "Generate a new client secret".
   - **Clave secreta del proyecto de Plunk** (`sk_…`, en Settings → API Keys). Con varios proyectos en la misma instalación, ver §8.
   - **Pegar en Dokploy** `PLUNK_MCP_API_KEY`, `GITHUB_CLIENT_ID` y `GITHUB_CLIENT_SECRET`, y desplegar.
6. **Cloudflare:** comprueba que no bloquea `/.idp/` ni `/.auth/` (ver §7). Es el fallo más probable.

`GITHUB_ALLOWED_USERS` es la lista de usuarios de GitHub que pueden entrar. mcp-auth-proxy también admite Google u otro proveedor OIDC, y contraseña (`PASSWORD`); GitHub es lo más sencillo de configurar y suele tener la verificación en dos pasos activada.

## 4. Conectar en claude.ai

Ajustes → Conectores → Añadir conector personalizado, con la URL `https://envio-mcp.<dominio>/mcp`.

- **Opción de cliente OAuth: "Registrar automáticamente" (DCR).** Es la que detecta claude.ai y la correcta con este proxy.
  - "Usar la identidad publicada de Claude" (CIMD) no la admite mcp-auth-proxy.
  - "Usar tu propio cliente OAuth" no aporta nada aquí.
- Al conectar, claude.ai abre el login de GitHub y después una página "Authorize": hay que pulsarla.
- El conector también aparece en Claude Code si la persona usa la misma cuenta.

## 5. Confirmación de envíos (importante)

`@plunk/mcp` pide confirmación humana (elicitation) antes de estas acciones:
- un email a más de un destinatario;
- `plunk_send_campaign`;
- activar un workflow que envía emails;
- cambiar el disparador de un workflow activo con emails;
- `plunk_start_workflow_execution`.

**claude.ai no admite elicitation.** En octubre de 2026 se conectaba con el protocolo 2026-07-28 y clientInfo `Anthropic/ClaudeAI`, con capacidades `{}` o solo la extensión ui. Por eso esas acciones fallan con `-32021 … do not declare the required capability`, sin enviar nada.

Decide con la persona:

| Opción | Cómo | Consecuencia |
|---|---|---|
| Mantenerlas bloqueadas | `PLUNK_ALLOW_UNCONFIRMED_SENDS=false` | Desde Claude se prepara todo (borradores, plantillas, workflows, copia de prueba con `plunk_test_campaign`, email a una persona); los envíos masivos se lanzan desde el panel de Plunk |
| Permitirlas | `PLUNK_ALLOW_UNCONFIRMED_SENDS=true` | Todo desde Claude. La protección pasa a ser el aviso de permiso de Claude antes de cada herramienta |

Si se permiten, recomienda dejar en "pedir permiso" (no "permitir siempre") en la configuración del conector en claude.ai:
- **Envíos:** `plunk_send_email`, `plunk_send_campaign`, `plunk_set_workflow_enabled`, `plunk_start_workflow_execution`, `plunk_update_workflow`.
- **Eventos:** `plunk_track_event`, porque puede disparar workflows que envían.
- **Consentimiento:** `plunk_subscribe_contact` (suscribir a alguien requiere su consentimiento) y `plunk_unsubscribe_contact`.
- **Borrados o cancelaciones:** `plunk_delete_contact`, `plunk_delete_workflow`, `plunk_delete_workflow_step`, `plunk_disconnect_workflow_steps`, `plunk_cancel_campaign`, `plunk_cancel_workflow_executions`.

El aviso de Claude muestra los argumentos, pero no cuántas personas recibirán una campaña. Antes de aprobar un `plunk_send_campaign`, que Claude diga el tamaño de la audiencia (`plunk_get_campaign` lo incluye).

## 6. Comprobar y probar

- **Sin login:** `https://envio-mcp.<dominio>/.well-known/oauth-protected-resource` debe dar 200, y `POST /mcp` sin token, 401.
- **Registro sin bloqueo:** `POST /.idp/register` debe responder JSON del proxy, no la página "Attention Required" de Cloudflare.
- **Log de `plunk-mcp`:** al arrancar, `escuchando en :3000 api=…`. Al conectar un cliente, `cliente (protocolo nuevo): …` o `initialize: …` con sus capacidades. Ahí se ve si un cliente admite elicitation.
- **Prueba de envío sin riesgo:** `plunk_send_email` a `success@simulator.amazonses.com` y `success+2@simulator.amazonses.com`, desde un dominio verificado. En el log de Plunk deben salir dos `Delivery confirmed`. Deja dos contactos del simulador en el proyecto; avisa a la persona.

## 7. Problemas conocidos

| Síntoma | Causa | Arreglo |
|---|---|---|
| claude.ai: "No se pudo registrar con el servicio de inicio de sesión…" y en el log del proxy no aparece ningún `/.idp/register` | Una regla del WAF de Cloudflare bloquea las rutas que empiezan por `/.` (una regla habitual contra `/.env`, `/.git`…). mcp-auth-proxy usa `/.idp/*` y `/.auth/*`, que no se pueden cambiar | En la condición de la regla que bloquea `/.`, añade `and http.host ne "envio-mcp.<dominio>"`. Si el editor rechaza la expresión, prueba esa forma simple antes que un `not (…)` anidado. Alternativa: registro A `envio-mcp` en nube gris. La regla es por zona: repítelo en cada dominio |
| Envíos masivos fallan con `-32021` | El cliente no admite confirmación | §5 |
| El conector deja de funcionar tras redesplegar | Se recreó `plunk-mcp-auth` y se perdieron sus datos | Sus claves y tokens están en el volumen `auth_data`; no lo borres. Si se pierde, reconecta el conector |
| 401 al usar el MCP con la sesión iniciada | Usuario de GitHub fuera de `GITHUB_ALLOWED_USERS` | Añádelo (separado por comas) y despliega |

## 8. Mantenimiento

- **Versiones fijadas** en `server.mjs` y el Dockerfile: `@plunk/mcp@0.17.0`, `@modelcontextprotocol/server@2.4.0`, `@modelcontextprotocol/node@2.1.2` y `mcp-auth-proxy:2.10.2`.
  - Al actualizar Plunk, sube `@plunk/mcp` a la misma versión.
  - Comprueba que `@plunk/mcp` sigue exponiendo `buildServer` (export principal) y `dist/config.js` (`loadConfig`), que usa `server.mjs`.
- **Varios proyectos en la misma instalación:** `@plunk/mcp` admite `PLUNK_API_KEY_<NOMBRE>` por proyecto, y cada herramienta pide entonces el argumento `project`. Habría que añadir esas variables a la sección `environment` de `plunk-mcp` y quitar `PLUNK_MCP_API_KEY`, que no se puede combinar con claves por nombre.
- **Una instalación de Plunk = un compose `plunk-mcp`**, con su dominio, su app de GitHub (la callback es única por dominio) y su conector en claude.ai.
