#!/usr/bin/env python3
"""Genera el env de Plunk para Dokploy con secretos internos nuevos.

Escribe el archivo con permisos 600 y muestra solo los nombres de las variables,
nunca los valores. Las claves de AWS quedan como PEGAR_EN_DOKPLOY y las del bucket
de imágenes (S3_ACCESS_KEY_ID, S3_ACCESS_KEY_SECRET) vacías: las pega la persona en la
pestaña Environment de Dokploy. Con las del bucket vacías, Plunk arranca sin subidas
de imágenes.

Ejemplo:
    python3 render_env.py --domain example.com --prefix envio --region eu-north-1 \
        --s3-endpoint https://<account_id>.r2.cloudflarestorage.com --s3-bucket envio-example --out plunk.env
    python3 render_env.py --panel mail.example.com --api mail-api.example.com \
        --files mail-files.example.com --region eu-west-1 --out plunk.env
"""

import argparse
import os
import secrets
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--domain", help="dominio base, p. ej. example.com (con --prefix genera los tres subdominios)")
    p.add_argument("--prefix", default="envio", help="prefijo de los subdominios (por defecto: envio)")
    p.add_argument("--panel", help="dominio del panel (sobrescribe el calculado)")
    p.add_argument("--api", help="dominio de la API (sobrescribe el calculado)")
    p.add_argument("--files", help="dominio público del bucket de imágenes (sobrescribe el calculado)")
    p.add_argument("--s3-endpoint", default="", help="endpoint S3 del bucket de imágenes, p. ej. https://<account_id>.r2.cloudflarestorage.com")
    p.add_argument("--s3-bucket", default="", help="nombre del bucket de imágenes")
    p.add_argument("--region", required=True, help="región de AWS SES, p. ej. eu-north-1")
    p.add_argument("--out", required=True, help="archivo de salida (se crea con permisos 600)")
    p.add_argument("--force", action="store_true", help="sobrescribir el archivo si ya existe")
    a = p.parse_args()

    if not (a.panel and a.api and a.files) and not a.domain:
        p.error("indica --domain, o los tres --panel, --api y --files")
    panel = a.panel or f"{a.prefix}.{a.domain}"
    api = a.api or f"{a.prefix}-api.{a.domain}"
    files = a.files or f"{a.prefix}-files.{a.domain}"
    for host in (panel, api, files):
        # Cloudflare Universal SSL solo cubre *.dominio; avisar si el host tiene más niveles
        if a.domain and host.endswith("." + a.domain) and "." in host[: -len(a.domain) - 1]:
            print(f"AVISO: {host} tiene más de un nivel bajo {a.domain}; el certificado gratuito de Cloudflare no lo cubre", file=sys.stderr)

    if os.path.exists(a.out) and not a.force:
        sys.exit(f"{a.out} ya existe; usa --force para regenerarlo (cambiaría las contraseñas de una instalación existente)")

    # Hex para que las contraseñas puedan ir dentro de DATABASE_URL sin escapar nada
    values = [
        ("DB_PASSWORD", secrets.token_hex(24)),
        ("JWT_SECRET", secrets.token_hex(32)),
        ("DASHBOARD_DOMAIN", panel),
        ("API_DOMAIN", api),
        ("LANDING_DOMAIN", "landing.plunk.internal"),
        ("WIKI_DOMAIN", "docs.plunk.internal"),
        ("LANDING_URI", f"https://{panel}"),
        ("WIKI_URI", f"https://{panel}"),
        ("USE_HTTPS", "true"),
        ("AWS_SES_REGION", a.region),
        ("AWS_SES_ACCESS_KEY_ID", "PEGAR_EN_DOKPLOY"),
        ("AWS_SES_SECRET_ACCESS_KEY", "PEGAR_EN_DOKPLOY"),
        ("SES_CONFIGURATION_SET", "plunk-configuration-set"),
        ("SES_CONFIGURATION_SET_NO_TRACKING", "plunk-no-tracking-configuration-set"),
        ("S3_ENDPOINT", a.s3_endpoint),
        ("S3_BUCKET", a.s3_bucket),
        ("S3_ACCESS_KEY_ID", ""),
        ("S3_ACCESS_KEY_SECRET", ""),
        ("S3_PUBLIC_URL", f"https://{files}"),
        ("DISABLE_SIGNUPS", "false"),
        ("AUTO_PROJECT_DISABLE", "false"),
        ("SHOW_SPONSOR", "false"),
    ]
    fd = os.open(a.out, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write("".join(f"{k}={v}\n" for k, v in values))
    os.chmod(a.out, 0o600)

    print(f"Escrito {a.out} (permisos 600) con: " + ", ".join(k for k, _ in values))
    print(f"Dominios en Dokploy: {panel} y {api} -> servicio plunk, puerto 80")
    print(f"{files}: dominio propio del bucket de imágenes (en R2: Settings -> Custom Domains), no va en Dokploy")
    if not (a.s3_endpoint and a.s3_bucket):
        print("AVISO: faltan --s3-endpoint o --s3-bucket; rellena S3_ENDPOINT y S3_BUCKET en el env antes de pegar las claves", file=sys.stderr)


if __name__ == "__main__":
    main()
