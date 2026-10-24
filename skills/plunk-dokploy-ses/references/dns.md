# DNS para Plunk (con notas de Cloudflare)

## Índice
1. Los dos tipos de registros
2. Registros de la instalación (panel, API, imágenes)
3. Registros del dominio de envío
4. Errores que ya han pasado
5. DMARC
6. Comprobar

## 1. Los dos tipos de registros

- **Instalación:** los tres nombres que apuntan al servidor (panel, API, imágenes). Se crean una vez.
- **Envío:** los que Plunk muestra al añadir un dominio de envío en su panel (Settings → Domains). Uno por cada dominio desde el que se envía.

Son cosas distintas: el dominio de la instalación aparece en los enlaces de baja y en las imágenes; el de envío, en el remitente (`hola@news.example.com`).

## 2. Registros de la instalación

Tres registros A (o CNAME) hacia la IP del servidor, o un comodín `*.example.com` que ya los cubra:

| Nombre | Destino | Servicio en Dokploy |
|---|---|---|
| `envio` | IP del servidor | `plunk`, puerto 80 |
| `envio-api` | IP del servidor | `plunk`, puerto 80 (el nginx interno separa panel y API por dominio) |
| `envio-files` | IP del servidor | `plunk-minio`, puerto 9000 |

**Un solo nivel de subdominio** (`envio-api.example.com`, no `api.envio.example.com`): el certificado gratuito de Cloudflare (Universal SSL) solo cubre `*.example.com`. Con otros proveedores DNS sin proxy da igual, pero mantener un nivel evita sorpresas.

**Cloudflare:** estos tres pueden ir con la nube naranja (proxy). Funcionó con proxy y el certificado de Let's Encrypt que emite Traefik en el servidor. El modo SSL/TLS de la zona debe ser **Full** o **Full (strict)**: con **Flexible**, Cloudflare habla con el servidor por HTTP, Traefik redirige a HTTPS y se forma un bucle de redirecciones. Si Let's Encrypt no consigue emitir el certificado, pon la nube gris un momento y vuelve a desplegar.

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
| Se añadió como dominio de envío el nombre del panel (`envio.example.com`) | Los emails saldrían como `@envio.example.com`, y el panel puede dejar de resolver: al crear registros por debajo de un nombre que dependía del comodín, ese nombre pasa a "existir" y, según el estándar DNS, el comodín deja de cubrirlo | Nunca uses `envio`, `envio-api` ni `envio-files` como dominio de envío ni como MAIL FROM. Borra el dominio en Plunk antes de crear sus registros y añade uno dedicado |
| Correo entrante que rebota en un dominio con buzón | Se añadió el MX opcional "Inbound email" en la raíz | Bórralo |
| Tras borrar y volver a añadir un dominio en Plunk, DKIM vuelve a PENDING | Al borrarlo, Plunk borra la identidad en SES; la nueva tiene tokens DKIM nuevos | Sustituye los tres CNAME por los nuevos |

Un dominio solo puede estar en **un proyecto** de Plunk. Si dos marcas comparten público, mételas en el mismo proyecto con sus dos dominios; los contactos y las bajas son por proyecto.

## 5. DMARC

Gmail y Yahoo exigen DMARC para envíos masivos. Si el dominio no tiene, empieza con:

| Tipo | Nombre | Valor |
|---|---|---|
| TXT | `_dmarc` (en la raíz del dominio) | `v=DMARC1; p=none;` |

Un `rua=mailto:...` solo tiene sentido si ese buzón existe. Si el dominio ya tiene `p=reject` o `p=quarantine`, no envíes nada hasta que SES marque DKIM como `SUCCESS`: con DKIM roto, esos emails se rechazan directamente.

## 6. Comprobar

```bash
bash scripts/check_dns.sh news.example.com eu-north-1 <token1> <token2> <token3>
```

Pregunta a los servidores autoritativos de la zona y a 1.1.1.1 y 8.8.8.8, indica en qué zona deben crearse los registros y cómo se escriben los nombres, y avisa de un MX de "inbound" o de la falta de DMARC. Cuando los 20 resultados salen bien, SES suele marcar DKIM y MAIL FROM como `SUCCESS` en minutos u horas (lo recomprueba él solo; `ses_check.snippet.py` lo confirma).
