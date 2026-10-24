#!/usr/bin/env python3
"""Ejecuta un *.snippet.py en local con boto3, para quien no tenga el MCP oficial de AWS.

Los snippets están escritos para run_script del MCP de AWS (await en el nivel
superior, call_boto3 y `result` como última expresión). Este programa los
ejecuta igual con un perfil local del AWS CLI.

Ejemplo:
    python3 run_snippet.py ses_check.snippet.py --profile mi-perfil \
        --set REGION=eu-north-1 --set ACCOUNT_ID=123456789012
    python3 run_snippet.py ses_setup.snippet.py --profile mi-perfil \
        --set REGION=eu-north-1 --set ACCOUNT_ID=123456789012 \
        --set SERVER_IP=203.0.113.10 --set API_DOMAIN=envio-api.example.com

Requisitos: Python 3.8+ y boto3 (pip install boto3), con el perfil ya iniciado
(aws login --profile ..., aws sso login --profile ..., o claves en ~/.aws).
"""

import argparse
import ast
import asyncio
import collections
import datetime
import json
import re
import sys
from pathlib import Path


def build_call_boto3(session, default_region):
    clients = {}

    async def call_boto3(*, service_name, operation_name, region_name=None, params=None):
        region = region_name or default_region
        key = (service_name, region)
        if key not in clients:
            clients[key] = session.client(service_name, region_name=region)
        client = clients[key]
        # Nombre de la operación (PascalCase) -> método de boto3 (snake_case)
        method = {v: k for k, v in client.meta.method_to_api_mapping.items()}.get(operation_name)
        if not method:
            raise ValueError(f"{service_name} no tiene la operación {operation_name}")
        fn = getattr(client, method)
        params = params or {}
        if client.can_paginate(method):
            pages = client.get_paginator(method).paginate(**params)
            merged = pages.build_full_result()
            return merged
        return fn(**params)

    return call_boto3


def render(source, values):
    for k, v in values.items():
        source = source.replace(f"__{k}__", v)
    missing = sorted(set(re.findall(r'"[^"\n]*__([A-Z_]+)__[^"\n]*"', source)))
    if missing:
        sys.exit("Faltan valores: " + ", ".join(f"--set {m}=..." for m in missing))
    return source


async def run(source, call_boto3):
    # Ejecutar el snippet es justo lo que hace este programa: solo pásale snippets de esta skill
    code = compile(source, "<snippet>", "exec", flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    scope = {
        "call_boto3": call_boto3, "asyncio": asyncio, "json": json, "re": re,
        "collections": collections, "datetime": datetime, "__name__": "__snippet__",
    }
    coro = eval(code, scope)
    if coro is not None:
        await coro
    return scope.get("result")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("snippet", help="archivo *.snippet.py")
    p.add_argument("--profile", required=True, help="perfil del AWS CLI")
    p.add_argument("--set", action="append", default=[], metavar="CLAVE=VALOR",
                   help="valor para un marcador __CLAVE__ (repetible)")
    a = p.parse_args()

    values = {}
    for item in a.set:
        if "=" not in item:
            p.error(f"--set necesita CLAVE=VALOR: {item}")
        k, v = item.split("=", 1)
        values[k.strip().upper()] = v.strip()
    if "REGION" not in values:
        p.error("falta --set REGION=...")

    import boto3  # importado aquí para que --help funcione sin boto3

    session = boto3.Session(profile_name=a.profile)
    source = render(Path(a.snippet).read_text(), values)
    result = asyncio.run(run(source, build_call_boto3(session, values["REGION"])))
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
