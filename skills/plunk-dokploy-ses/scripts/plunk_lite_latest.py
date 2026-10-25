#!/usr/bin/env python3
"""Dice a qué versión apunta ghcr.io/joanproductivo/plunk-lite:latest.

`latest` siempre es la última Plunk Lite, pero en el compose conviene fijar la versión
concreta (sha-<commit>) para que un despliegue no la cambie sin querer. Este script lee
la imagen `latest` en el registro público, sin credenciales ni Docker, y muestra la
etiqueta que hay que poner en el compose, el commit y la fecha de compilación.

Ejemplo:
    python3 plunk_lite_latest.py            # imprime p. ej. sha-4f7a055 y los detalles
    python3 plunk_lite_latest.py --tag-only # imprime solo la etiqueta
"""

import argparse
import json
import sys
import urllib.error
import urllib.request

REPO = "joanproductivo/plunk-lite"
REGISTRY = "https://ghcr.io"
INDEX_TYPES = ",".join(
    [
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    ]
)


def get_json(url, token=None, accept=None):
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    if accept:
        req.add_header("Accept", accept)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--tag-only", action="store_true", help="imprime solo la etiqueta sha-<commit>")
    p.add_argument("--tag", default="latest", help="etiqueta que se consulta (por defecto: latest)")
    args = p.parse_args()

    token = get_json(f"{REGISTRY}/token?scope=repository:{REPO}:pull")["token"]
    try:
        manifest = get_json(f"{REGISTRY}/v2/{REPO}/manifests/{args.tag}", token, INDEX_TYPES)
    except urllib.error.HTTPError as err:
        if err.code == 404:
            sys.exit(
                f"No existe la etiqueta {args.tag} de {REPO}. Busca la más reciente en "
                f"https://github.com/{REPO}/pkgs/container/plunk-lite"
            )
        raise

    # latest es un índice multiplataforma: todas las plataformas salen del mismo commit
    if "manifests" in manifest:
        platforms = [m for m in manifest["manifests"] if m.get("platform", {}).get("os") != "unknown"]
        manifest = get_json(f"{REGISTRY}/v2/{REPO}/manifests/{platforms[0]['digest']}", token, INDEX_TYPES)

    config = get_json(f"{REGISTRY}/v2/{REPO}/blobs/{manifest['config']['digest']}", token)
    labels = config.get("config", {}).get("Labels") or {}
    revision = labels.get("org.opencontainers.image.revision")
    if not revision:
        sys.exit(f"La imagen {args.tag} no lleva la etiqueta org.opencontainers.image.revision")

    tag = f"sha-{revision[:7]}"
    if args.tag_only:
        print(tag)
        return

    print(f"Etiqueta para el compose: ghcr.io/{REPO}:{tag}")
    print(f"Commit: https://github.com/{REPO}/commit/{revision}")
    print(f"Compilada: {labels.get('org.opencontainers.image.created', 'desconocido')}")


if __name__ == "__main__":
    main()
