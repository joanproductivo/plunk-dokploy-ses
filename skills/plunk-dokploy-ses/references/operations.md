# Mantenimiento de una instalación de Plunk en Dokploy

## Índice
1. Qué corre y cuánto ocupa
2. Arranque recortado
3. Actualizar Plunk
4. Variables de entorno, reiniciar y desplegar
5. Copias de seguridad
6. Imágenes del editor (R2 u otro S3)
7. ntfy (avisos push)
8. Cambiar de dominio más adelante
9. Abrir registros para otra persona
10. Segunda instalación en el mismo servidor

## 1. Qué corre y cuánto ocupa

Medido con Plunk 0.17.0. El contenedor `plunk` lleva varios programas Node.js gestionados por PM2:

| Proceso | Qué hace | Memoria propia |
|---|---|---|
| api | API pública y webhooks de SNS | ~71 MB |
| worker | Colas: envíos, campañas, workflows | ~62 MB |
| web | El panel | ~51 MB |
| pm2 + nginx | Supervisor y enrutado por dominio | ~28 MB |
| wiki, landing, smtp | Docs, web promocional, relay SMTP | ~104 MB (quitados por el arranque recortado) |

Contenedor: ~330 MB con todo, ~190 MB recortado. Además: Postgres ~98 MB y Redis ~7 MB. Una instalación completa recortada ronda los 300 MB (MinIO, si se monta, suma ~90 MB).

Disco: Docker no limita por defecto el log de cada contenedor (el healthcheck ya escribe ~1 MB al día y cada email añade varias líneas). La plantilla lo deja en 3 ficheros de 10 MB por servicio (como mucho ~120 MB por instalación). Para comprobarlo, `HostConfig.LogConfig.Config` del contenedor (docker inspect, o `docker-getConfig` en el MCP de Dokploy) debe mostrar `max-size` y `max-file`; si sale vacío, el compose desplegado no lleva el bloque `logging`. Plunk guarda los eventos en Postgres, así que rotar el log no pierde nada importante.

## 2. Arranque recortado

El compose sustituye `entrypoint`/`command` del servicio `plunk`: copia el script original `/usr/local/bin/docker-entrypoint-nginx.sh`, quita con `sed` la preparación de landing y wiki, y antes de `exec pm2-runtime start /tmp/ecosystem.config.js` ejecuta un filtro que elimina `landing`, `wiki` y `smtp` de la configuración de PM2.

- Log esperado: `Plunk: arrancando nginx, api, worker, web`.
- Si una versión nueva cambia el script y el parche no encaja, el log dice `AVISO: el parche de arranque no aplica a esta versión de Plunk; arrancando todos los servicios` y Plunk arranca completo (funciona, solo gasta más memoria).
- Para volver al arranque original: borra `entrypoint` y `command` del servicio `plunk` y despliega.

## 3. Actualizar Plunk

La versión está fijada en el compose (`image: ghcr.io/useplunk/plunk:0.17.0`), así que actualizar es un cambio del compose, no del env. Con Plunk Lite, sigue references/plunk-lite.md §5.

1. Lee las notas de versión entre la versión actual y la nueva (https://github.com/useplunk/plunk/releases): migraciones, variables nuevas, cambios de comportamiento.
2. Comprueba que el parche de arranque sigue aplicando. Con Docker en cualquier máquina:
   ```bash
   docker run --rm --entrypoint cat ghcr.io/useplunk/plunk:NUEVA /usr/local/bin/docker-entrypoint-nginx.sh | grep -n 'replace_urls_in_app "landing"\|replace_urls_in_app "wiki"\|^exec pm2-runtime start /tmp/ecosystem.config.js$'
   ```
   Deben salir las tres líneas. Si el script ya no está en esa ruta, quita el bloque `entrypoint`/`command` antes de actualizar (si no, el contenedor no arrancaría).
3. Haz una copia de Postgres (sección 5).
4. Cambia la etiqueta de la imagen en el compose y despliega.
5. Verifica: log `Plunk: arrancando nginx, api, worker, web`, `https://<API_DOMAIN>/health` da 200, el panel carga y la cuota de SES aparece en el log.
6. Si la versión nueva necesita variables nuevas: la persona las añade en Dokploy y tú las añades a la sección `environment` del compose (si no están ahí, no llegan al contenedor).

## 4. Variables de entorno, reiniciar y desplegar

- **Antes de que la persona pegue las claves de AWS**, puedes guardar el env por la API de Dokploy con el archivo completo que generaste.
- **Después, no.** Dokploy devuelve los secretos ocultos; al guardar, sobrescribirías las claves. Pide a la persona el cambio: compose → Environment → editar → Save → Deploy. Si alguna vez se pisan, la solución es que vuelva a pegar las claves.
- Los cambios de env y de compose se aplican con **Deploy**. **Reiniciar** el contenedor no los aplica, pero sirve para que Plunk relea la cuota de SES.
- Al quitar un servicio del compose y desplegar, Dokploy elimina su contenedor, pero sus volúmenes quedan. Bórralos solo si la persona lo confirma.

## 5. Copias de seguridad

Todo lo importante (contactos, plantillas, campañas, eventos, workflows) está en Postgres. Redis solo guarda colas.

- En Dokploy: Settings → Destinations para crear un destino S3 (Cloudflare R2, AWS S3, Backblaze…); luego en el compose → Backups, una copia programada de la base de datos `plunk` (servicio `plunk-postgres`, usuario `plunk`), por ejemplo diaria.
- Las imágenes del editor están en el bucket externo (sección 6), fuera del servidor. Si se usa MinIO, copia también su volumen (volume backups de Dokploy).
- Prueba a restaurar una vez: una copia que nunca se ha restaurado es una suposición.

## 6. Imágenes del editor (R2 u otro S3)

Plunk sube las imágenes del editor (plantillas y campañas) a un almacenamiento S3 y las enlaza en los emails con `S3_PUBLIC_URL`. Se configura con cinco variables, **todas en el env** (el compose solo las lee con `${…}`), más `S3_FORCE_PATH_STYLE: "true"` fijo en el compose:

| Variable | Valor con Cloudflare R2 |
|---|---|
| `S3_ENDPOINT` | `https://<account_id>.r2.cloudflarestorage.com` |
| `S3_BUCKET` | nombre del bucket |
| `S3_ACCESS_KEY_ID` / `S3_ACCESS_KEY_SECRET` | claves de un token de R2 con lectura y escritura solo en ese bucket (las pega la persona) |
| `S3_PUBLIC_URL` | `https://envio-files.<dominio>` (el dominio propio del bucket, sin barra final) |

Si faltan las claves, Plunk arranca igual con `File uploads (S3) ❌` y el editor no ofrece subir imágenes. Al arrancar con claves, Plunk comprueba el bucket (lo crea si no existe) e intenta aplicarle una política pública. R2 no admite esa operación: sale `[S3] Failed to set bucket policy: NotImplemented`, que es inofensivo, y por eso el bucket se hace público desde R2 con el dominio propio. Las imágenes quedan en `<S3_PUBLIC_URL>/<id del proyecto>/<fecha>-<hash>.<ext>`.

**Cambiar de bucket o de proveedor:** las imágenes ya enviadas apuntan a la URL vieja y se romperían. Antes de cambiar, copia los objetos al bucket nuevo con la misma ruta y conserva el dominio (o mantén el viejo un tiempo). Si solo eran pruebas, basta con cambiar las variables y desplegar.

**Alternativa sin servicio externo: MinIO en el servidor.** Gasta ~90 MB de memoria y deja las imágenes en un volumen que hay que copiar aparte. Añade al compose un servicio `plunk-minio` (imagen `pgsty/minio`, `command: server /data --console-address ":9001"`, `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` del env, volumen en `/data` y healthcheck a `http://localhost:9000/minio/health/live`), su `depends_on` desde `plunk` y su volumen. En el env: `S3_ENDPOINT=http://plunk-minio:9000`, `S3_BUCKET=uploads`, `S3_ACCESS_KEY_ID`/`S3_ACCESS_KEY_SECRET` con los mismos valores que `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`, y `S3_PUBLIC_URL=https://envio-files.<dominio>/uploads`. En Dokploy, el dominio `envio-files.<dominio>` va al servicio `plunk-minio`, puerto 9000. Para quitarlo después, borra antes ese dominio en Dokploy: si no, el despliegue falla con `Domain "…" is attached to service "plunk-minio" which does not exist in the compose`.

**Sin subidas:** deja las claves vacías. Se usan imágenes por URL (de una web, por ejemplo).

## 7. ntfy (avisos push)

La plantilla no incluye ntfy. Plunk envía avisos como "New User Signup", "Campaign Sending Started" o "Email Bounces" a ntfy si existe la variable `NTFY_URL`; sin ella, simplemente no los envía. Si la persona los quiere en el móvil: usa ntfy.sh con un topic difícil de adivinar (quien lo conozca puede leerlos) o un ntfy propio con contraseña, y añade `NTFY_URL: ${NTFY_URL:-}` a la sección `environment` del compose.

## 8. Cambiar de dominio más adelante

Técnicamente es cambiar los dominios en Dokploy y las variables, pero:
- Los **enlaces de baja** de los emails ya enviados apuntan al dominio del panel, y la baja tiene que seguir funcionando (obligación legal).
- Las **imágenes** se guardan con la URL completa en plantillas y emails enviados.
- La **suscripción SNS** apunta a la API: crea la nueva (ejecuta `ses_setup` con el nuevo `API_DOMAIN`) y borra la vieja después.
- Las **integraciones** (webs, n8n, formularios) llaman a la URL de la API.

Solución: mantener los dominios viejos y los nuevos a la vez en Dokploy durante unos meses. Por eso conviene elegir bien el dominio desde el principio.

## 9. Abrir registros para otra persona

`DISABLE_SIGNUPS=false` → Deploy → la persona se registra → `DISABLE_SIGNUPS=true` → Deploy. Revisa en el log que solo hubo los registros esperados. Si las claves de AWS ya están pegadas, estos cambios los hace la persona en la interfaz (sección 4).

## 10. Segunda instalación en el mismo servidor

Para otra cuenta de AWS (otra empresa, otra factura): otro compose en Dokploy con la misma plantilla, otros dominios, otro env generado con `render_env.py` y su propia configuración de SES en su cuenta. Comparte las imágenes de Docker, así que apenas ocupa disco; en memoria, unos 400 MB más.
