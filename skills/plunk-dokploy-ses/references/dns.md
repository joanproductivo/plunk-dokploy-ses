# DNS para Plunk (con notas de Cloudflare)

## Índice
1. Los dos tipos de registros
2. Registros de la instalación (panel, API, imágenes)
3. Registros del dominio de envío
4. Errores que ya han pasado
5. DMARC
6. Comprobar
7. Un subdominio para transaccional y otro para marketing
8. Crear los registros con el MCP de Cloudflare

## 1. Los dos tipos de registros

- **Instalación:** los tres nombres que apuntan al servidor (panel, API, imágenes). Se crean una vez.
- **Envío:** los que Plunk muestra al añadir un dominio de envío en su panel (Settings → Domains). Uno por cada dominio desde el que se envía.

Son cosas distintas: el dominio de la instalación aparece en los enlaces de baja y en las imágenes; el de envío, en el remitente (`hola@news.example.com`).

## 2. Registros de la instalación

Dos registros A (o CNAME) hacia la IP del servidor, o un comodín `*.example.com` que ya los cubra, más el dominio de las imágenes, que apunta al bucket:

| Nombre | Destino | Servicio en Dokploy |
|---|---|---|
| `envio` | IP del servidor | `plunk`, puerto 80 |
| `envio-api` | IP del servidor | `plunk`, puerto 80 (el nginx interno separa panel y API por dominio) |
| `envio-files` | El bucket de R2 (lo crea R2 al conectarlo como dominio propio; anula el comodín) | No va en Dokploy |

**Un solo nivel de subdominio** (`envio-api.example.com`, no `api.envio.example.com`): el certificado gratuito de Cloudflare (Universal SSL) solo cubre `*.example.com`. Con otros proveedores DNS sin proxy da igual, pero mantener un nivel evita sorpresas.

**Cloudflare:** el panel y la API pueden ir con la nube naranja (proxy). Funcionó con proxy y el certificado de Let's Encrypt que emite Traefik en el servidor. El modo SSL/TLS de la zona debe ser **Full** o **Full (strict)**: con **Flexible**, Cloudflare habla con el servidor por HTTP, Traefik redirige a HTTPS y se forma un bucle de redirecciones. Si Let's Encrypt no consigue emitir el certificado, pon la nube gris un momento y vuelve a desplegar.

## 3. Registros del dominio de envío

Usa un **subdominio dedicado** (`news.example.com`, `mail.example.com`…), distinto de los tres de la instalación. Aísla la reputación del dominio principal y no interfiere con el correo que ya tenga la raíz. Enviar desde la raíz también funciona, pero entonces cualquier error de DNS afecta al dominio principal.

Para `news.example.com` en la región `eu-north-1`, Plunk pide (todos **DNS only / nube gris**):

| Tipo | Nombre en Cloudflare (zona example.com) | Valor | Notas |
|---|---|---|---|
| CNAME | `<token1>._domainkey.news` | `<token1>.dkim.amazonses.com` | DKIM. Con nube naranja Cloudflare oculta el CNAME y no verifica |
| CNAME | `<token2>._domainkey.news` | `<token2>.dkim.amazonses.com` | |
| CNAME | `<token3>._domainkey.news` | `<token3>.dkim.amazonses.com` | |
| MX | `plunk.news` | `feedback-smtp.eu-north-1.amazonses.com`, prioridad `10` | MAIL FROM (rebotes). La prioridad va en su propio campo |
| TXT | `plunk.news` | `v=spf1 include:amazonses.com ~all` | SPF del MAIL FROM |

- El prefijo `plunk.` es el subdominio de MAIL FROM por defecto (variable `MAIL_FROM_SUBDOMAIN`).
- Cloudflare añade el nombre de la zona solo: escribe `plunk.news`, no `plunk.news.example.com`, o acabará como `plunk.news.example.com.example.com`.
- Cloudflare **sí** admite nombres de varios niveles en registros DNS (`plunk.news`, `x._domainkey.news`). La limitación de un nivel es solo del certificado para webs con proxy.
- **No hace falta ningún registro A** para el dominio de envío: ahí no vive ninguna web.
- **El MX opcional "Inbound email"** (`inbound-smtp.<región>.amazonaws.com` en el propio dominio) sirve para que Plunk reciba emails como eventos de workflow. **No lo añadas** salvo que se haya configurado la recepción en SES a propósito: sin reglas de recepción el correo que llegue se pierde, y en un dominio que ya recibe correo (MX de su buzón) le quitaría parte del correo entrante.

En otros proveedores DNS los registros son los mismos; cambia cómo se escribe el nombre (algunos piden el nombre completo terminado en punto, otros solo la parte relativa).

## 4. Errores que ya han pasado

| Síntoma | Causa | Arreglo |
|---|---|---|
| SES no verifica y los registros "están" | Se crearon en **otra zona** de la misma cuenta de Cloudflare | Comprueba el nombre de la zona arriba en Cloudflare antes de añadir; borra los de la zona equivocada |
| DKIM `FAILED` | CNAME con nube naranja, o nombre sin la parte del subdominio (`<token>._domainkey` en vez de `<token>._domainkey.news`) | Nube gris y nombre completo relativo a la zona |
| Error al guardar el MX | Prioridad escrita dentro del valor (`10 feedback-smtp…`) o nombre con el dominio repetido | Prioridad en su campo; nombre relativo |
| Se añadió como dominio de envío el nombre del panel (`envio.example.com`) | Los emails saldrían como `@envio.example.com`, y el panel puede dejar de resolver: al crear registros por debajo de un nombre que dependía del comodín, ese nombre pasa a "existir" y, según el estándar DNS, el comodín deja de cubrirlo (en una prueba con comodín con proxy, Cloudflare siguió resolviéndolo; no cuentes con ello) | Nunca uses `envio`, `envio-api` ni `envio-files` como dominio de envío ni como MAIL FROM. Borra el dominio en Plunk antes de crear sus registros y añade uno dedicado |
| Correo entrante que rebota en un dominio con buzón | Se añadió el MX opcional "Inbound email" en la raíz | Bórralo |
| Tras borrar y volver a añadir un dominio en Plunk, DKIM vuelve a PENDING | Al borrarlo, Plunk borra la identidad en SES; la nueva tiene tokens DKIM nuevos | Sustituye los tres CNAME por los nuevos |

Un dominio solo puede estar en **un proyecto** de Plunk. Si dos marcas comparten público, mételas en el mismo proyecto con sus dos dominios; los contactos y las bajas son por proyecto.

## 5. DMARC

Gmail y Yahoo exigen DMARC para envíos masivos. Si el dominio no tiene, empieza con:

| Tipo | Nombre | Valor |
|---|---|---|
| TXT | `_dmarc` (en la raíz del dominio) | `v=DMARC1; p=none;` |

Un `rua=mailto:...` solo tiene sentido si ese buzón existe. Si el dominio ya tiene `p=reject` o `p=quarantine`, no envíes nada hasta que SES marque DKIM como `SUCCESS`: con DKIM roto, esos emails se rechazan directamente.

Los subdominios heredan el DMARC de la raíz, salvo que lleve `sp=` o tengan el suyo: no hace falta un `_dmarc` por cada dominio de envío. Tampoco hay que tocar el SPF de la raíz para enviar por SES, porque el SPF que cuenta es el de `plunk.<dominio de envío>`.

## 6. Comprobar

```bash
bash scripts/check_dns.sh news.example.com eu-north-1 <token1> <token2> <token3>
```

Pregunta a los servidores autoritativos de la zona y a 1.1.1.1 y 8.8.8.8, indica en qué zona deben crearse los registros y cómo se escriben los nombres, y avisa de un MX de "inbound" o de la falta de DMARC. Cuando los 20 resultados salen bien, SES suele marcar DKIM y MAIL FROM como `SUCCESS` en minutos u horas (lo recomprueba él solo; `ses_check.snippet.py` lo confirma).

## 7. Un subdominio para transaccional y otro para marketing

No es obligatorio: Plunk envía igual con un solo dominio. Es la práctica recomendada cuando una misma instalación manda las dos cosas, por ejemplo `hola@avisos.example.com` para accesos, recibos y códigos, y `hola@news.example.com` para boletines.

**Por qué:**
- **Marketing arriesga más.** Los boletines reciben muchas más quejas y borrados sin abrir que un email que la persona ha pedido. Gmail y otros proveedores valoran la reputación por dominio, así que una mala campaña no debería mandar a spam un enlace de acceso o un recibo.
- **Se puede ver cada tipo por separado.** Cada subdominio tiene su propia reputación en herramientas como Google Postmaster Tools, y un problema se localiza antes.
- **Cuesta poco.** Son los mismos 5 registros otra vez, y no tocan el correo de la raíz.

**Lo que no separa:**
- **La reputación del dominio principal.** Gmail también la tiene en cuenta, así que el aislamiento es parcial.
- **La cuenta de SES.** Las tasas de rebotes y quejas son de toda la cuenta: si AWS la pausa, se paran los dos tipos de email.
- **La supresión.** Quien se queja de un boletín queda suprimido en la cuenta y deja de recibir también los transaccionales (aws-ses.md §10).
- **Las IPs de envío**, salvo que se contraten IPs dedicadas y se separen por pools.
- **El proyecto de Plunk.** Si los dos dominios están en el mismo y `AUTO_PROJECT_DISABLE` lo desactiva, se para todo. Se puede usar un proyecto para cada uno, pero los contactos y las bajas son por proyecto.
- **El dominio de seguimiento**, que es único por configuration set (aws-ses.md §11). Con «Marketing only», los transaccionales de la API no lo usan.

Para separarlo todo hace falta otra cuenta de SES y otra instalación (operations.md §10). Con poco volumen no compensa.

**Cómo hacerlo:**
1. Elige dos subdominios, distintos de los de la instalación. Añade cada uno en Settings → Domains y crea sus registros (§3).
2. Cambia el remitente en las plantillas transaccionales, los workflows y las llamadas a `/v1/send`. Añadir el dominio no cambia nada por sí solo.
3. Pon una dirección de respuesta con buzón real (`reply` en la API, Reply-To en plantillas y campañas). Los subdominios de envío no tienen MX, así que no reciben las respuestas.
4. Si en una instalación que ya envía se mueve mucho volumen a un subdominio nuevo, hazlo poco a poco: empieza sin historial. Un transaccional de poco volumen se puede pasar de una vez.

**No choca con el buzón de la raíz** (Google Workspace, Stalwart u otro). Ese correo usa el MX, el SPF y el DKIM de la raíz, y Plunk solo crea nombres por debajo del subdominio de envío. Si algún día hay que recibir en ese subdominio, se añade su MX hacia el buzón; no choca con el de los rebotes, que está en `plunk.<subdominio>`.

## 8. Crear los registros con el MCP de Cloudflare

Si la persona usa Cloudflare, puede conectar su MCP oficial (`https://mcp.cloudflare.com/mcp`, con login OAuth en su navegador) y la IA crea los registros en lugar de copiarlos a mano, lo que evita erratas en los tokens. Es opcional: sin él, guíala por el panel. El permiso no pasa por el chat: si el login no incluye edición de DNS, pídele que lo vuelva a hacer con ese permiso, no que pegue un token.

El MCP expone `search`, para consultar la API, y `execute`, que ejecuta JavaScript con `cloudflare.request()`. Pasos:

1. **Busca la zona y revísala:** `GET /zones?name=example.com`. Comprueba que sale una sola y que su nombre es el esperado. Lista sus registros con `GET /zones/<id>/dns_records` (`per_page: 500`) y mira si ya existe alguno de los nombres, y qué hay en la raíz y en el comodín.
2. **Enseña a la persona los registros que vas a crear**, salvo que ya te haya pedido crearlos con esos valores.
3. **Crea cada uno** con `POST /zones/<id>/dns_records`. Copia los tokens tal como los da Plunk (panel o `plunk_list_domains`):
   ```js
   async () => {
     const zone = "<id>", dominio = "news.example.com", region = "eu-north-1";
     const comment = "Plunk: dominio de envío " + dominio;
     const recs = [
       ...["<token1>", "<token2>", "<token3>"].map(t => ({type: "CNAME", name: `${t}._domainkey.${dominio}`, content: `${t}.dkim.amazonses.com`, proxied: false, ttl: 1, comment})),
       {type: "MX", name: `plunk.${dominio}`, content: `feedback-smtp.${region}.amazonses.com`, priority: 10, ttl: 1, comment},
       {type: "TXT", name: `plunk.${dominio}`, content: "\"v=spf1 include:amazonses.com ~all\"", ttl: 1, comment},
     ];
     const out = [];
     for (const body of recs) {
       const r = await cloudflare.request({method: "POST", path: `/zones/${zone}/dns_records`, body});
       out.push([r.result.type, r.result.name, r.result.content, r.result.proxied]);
     }
     return out;
   }
   ```
4. **Comprueba** con `check_dns.sh` (§6) y deja que SES verifique. En la instalación de referencia tardó unos minutos. `plunk_check_domain` lo consulta, pero no lo llames en bucle.

**Diferencias con el panel:** en la API, `name` es el nombre **completo** (`plunk.news.example.com`), no el relativo que se escribe en el panel. `proxied: false` es la nube gris, obligatoria aquí.

**Límites:**
- Crear registros nuevos para un dominio de envío entra en lo que te pide la persona. Modificar o borrar registros existentes, o tocar el MX, el SPF o el DMARC de la raíz, necesita un sí expreso: puede cortar el correo o la web. Antes de borrar, enseña el registro.
- No crees el MX opcional de «Inbound email» (§3).
- Si `_dmarc` no existe, proponlo (§5) y créalo con su sí.
