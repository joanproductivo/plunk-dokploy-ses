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

Además lleva arreglos de fallos que la oficial aún no tiene. Por ejemplo, las aperturas automáticas que SES marca como tales ya no cuentan, las tasas del dashboard son correctas y se pueden alinear imágenes en el editor. La lista completa está en los commits del repositorio.

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

Sigue la Fase 1 de SKILL.md con dos cambios en `assets/docker-compose.yml`, antes de crear el compose en Dokploy:

1. Cambia la imagen del servicio `plunk` por la de Plunk Lite, con una etiqueta concreta:
   ```yaml
   image: ghcr.io/joanproductivo/plunk-lite:sha-4f7a055
   ```
   Plunk Lite solo publica etiquetas `sha-<commit>`, no versiones con nombre ni `latest`. Así la versión queda fijada igual que con la oficial. Para ver si hay una más nueva, mira la página del paquete: https://github.com/joanproductivo/plunk-lite/pkgs/container/plunk-lite
2. Borra el bloque `entrypoint`/`command` del servicio `plunk`, con sus tres líneas de comentario. La imagen ya arranca solo lo necesario. Si se deja, no rompe nada, pero sobra.

El resto no cambia: el env, MinIO o R2, los dominios, SES y el DNS.

**Verificación** (sustituye a la de la Fase 1):
- El contenedor `plunk` queda healthy.
- En el log no aparece `Plunk: arrancando…`. En su lugar, pm2 arranca exactamente tres procesos: `App [nginx:0] online`, `App [api:1] online` y `App [worker:2] online`.
- En el log aparecen `nginx: configuration file /etc/nginx/nginx.conf test is successful` y `URL replacement complete for web`. Si la configuración de nginx o el reemplazo de URLs fallan, el contenedor se para a propósito, en vez de quedarse a medias.
- `https://envio-api.<dominio>/health` responde 200 y `https://envio.<dominio>` muestra el login.

## 5. Actualizar

1. Busca la etiqueta más reciente en la página del paquete (sección 4) y lee en el repositorio qué cambió desde la que hay instalada.
2. Haz una copia de Postgres (operations.md §5).
3. Cambia la etiqueta de la imagen en el compose y despliega.
4. Verifica como en la sección 4. Si algo falla, vuelve a la etiqueta anterior con el mismo compose.

## 6. Volver a la imagen oficial

1. Haz una copia de Postgres.
2. Pon la imagen oficial (`ghcr.io/useplunk/plunk:<versión>`) en una versión igual o más nueva que la base de Plunk Lite. Si eliges una más antigua, la base de datos podría tener migraciones que esa versión no conoce.
3. Vuelve a poner el bloque `entrypoint`/`command` de `assets/docker-compose.yml`, o el contenedor arrancará también landing, wiki y SMTP.
4. Despliega y verifica como en la Fase 1 de SKILL.md.
