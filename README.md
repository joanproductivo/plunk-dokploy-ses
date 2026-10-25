# plunk-dokploy-ses

Skill para Claude que despliega y configura [Plunk](https://github.com/useplunk/plunk) self-hosted (email marketing y transaccional open source) en [Dokploy](https://dokploy.com) con AWS SES, de principio a fin.

> **English:** a Claude skill to self-host Plunk on Dokploy with AWS SES, end to end. The skill is written in Spanish, but Claude follows it in whatever language you use.

## Qué hace

- Despliega un compose de Plunk probado y recortado en memoria (unos 190 MB en lugar de 330 MB).
- Permite elegir entre la imagen oficial de Plunk y [Plunk Lite](https://github.com/joanproductivo/plunk-lite), un fork ligero y no oficial (Node 24, la mitad de tamaño, sin relay SMTP).
- Configura los dominios con Traefik y Let's Encrypt.
- Prepara AWS SES: un usuario IAM con permisos mínimos (solo desde la IP del servidor), los configuration sets y el topic SNS que lleva los eventos a Plunk.
- Te guía con los registros DNS del dominio de envío, incluidas las trampas de Cloudflare.
- Prueba los envíos en el sandbox de SES, pide la salida a producción y revisa el plan de precios.
- Explica cómo enviar desde una web por API, los workflows, las aperturas falsas y el mantenimiento.
- Publica el MCP de Plunk con login de GitHub para usarlo desde claude.ai.

Sale de dos instalaciones reales con Plunk 0.17.0 (octubre de 2026).

## Instalación

**En claude.ai o la app de Claude:** descarga `plunk-dokploy-ses.skill` de la [última versión](https://github.com/joanproductivo/plunk-dokploy-ses/releases/latest) y súbelo en la sección de Skills de la configuración (Settings → Capabilities).

**En Claude Code:**

```bash
git clone https://github.com/joanproductivo/plunk-dokploy-ses.git
cp -R plunk-dokploy-ses/skills/plunk-dokploy-ses ~/.claude/skills/
```

Después pídele a Claude, por ejemplo: «Instala Plunk en mi Dokploy con AWS SES».

## Qué necesitas

- Un servidor con Dokploy y un dominio.
- Una cuenta de AWS con SES en la región que elijas.
- Recomendado: el MCP de Dokploy y el MCP oficial de AWS conectados a Claude, para que haga los pasos por ti. Sin ellos, la skill te guía por las consolas.

## Seguridad

- La skill no pide claves por el chat: las access keys de AWS las creas tú en la consola y las pegas directamente en Dokploy.
- Antes de cualquier acción hacia fuera (pedir producción a AWS, cambiar el plan de precios, borrar recursos, publicar en GitHub) pide confirmación.
- No contiene datos de ninguna instalación real.

## Contenido

```
skills/plunk-dokploy-ses/
├── SKILL.md       las fases, de decidir a mantener
├── references/    AWS SES, DNS, uso de Plunk, MCP remoto, operaciones, Plunk Lite y problemas frecuentes
├── scripts/       configuración y comprobación de SES, comprobación de DNS, generación del env, última versión de Plunk Lite
└── assets/        compose de Plunk y del MCP remoto, plantillas de env
```

## Licencia

[MIT](LICENSE). Plunk y Plunk Lite tienen su propia licencia (AGPL-3.0): esta skill despliega sus imágenes publicadas y no incluye su código.
