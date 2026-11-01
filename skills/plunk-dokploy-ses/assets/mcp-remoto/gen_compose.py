# Genera docker-compose.yml con server.mjs incrustado en el Dockerfile (Dokploy raw no tiene repositorio)
#
#   python3 gen_compose.py                     # el MCP de Plunk Lite, en el commit de COMMIT
#   python3 gen_compose.py --commit <commit>   # el MCP de Plunk Lite, en ese commit
#   python3 gen_compose.py --npm <versión>     # @plunk/mcp de npm, solo con la imagen oficial
#
# El commit es el de la imagen desplegada (scripts/plunk_lite_latest.py lo imprime).
# Así el MCP conoce las funciones que esa API tiene y no pide ninguna que le falte.
import argparse
import re
import textwrap

COMMIT = '5892b47225e4fc1befd9b4cf47e307cc7c905247'

p = argparse.ArgumentParser(description='Genera el compose de plunk-mcp')
p.add_argument('salida', nargs='?', default='docker-compose.yml')
p.add_argument('--commit', default=COMMIT, help='compila el MCP de Plunk Lite en este commit')
p.add_argument('--npm', metavar='VERSION', help='usa @plunk/mcp de npm, solo con la imagen oficial')
args = p.parse_args()

srv = open('server.mjs').read()
assert '$' not in srv, 'server.mjs no puede llevar $: Compose lo interpretaría como variable'
ind = lambda s, n: textwrap.indent(s, ' ' * n)
SDK = '@modelcontextprotocol/server@2.4.0 @modelcontextprotocol/node@2.1.2'
SERVER = """RUN cat > /app/server.mjs <<'EOF'
""" + srv + """EOF
USER node
ENV NODE_ENV=production PORT=3000
CMD ["node", "/app/server.mjs"]
"""

if not args.npm:
    assert re.fullmatch(r'[0-9a-f]{7,40}', args.commit), 'el commit es un hash, como el que da plunk_lite_latest.py'
    # Fase de compilación: solo apps/mcp y la config de TypeScript que extiende. apps/mcp se saca del
    # monorepo porque, dentro, npm intenta instalar los workspaces de la raíz. El paquete
    # @plunk/typescript-config no está en npm, así que se quita de devDependencies y se copia a mano.
    dockerfile = """# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
ADD https://github.com/joanproductivo/plunk-lite/archive/""" + args.commit + """.tar.gz /tmp/src.tar.gz
RUN mkdir /src && tar -xzf /tmp/src.tar.gz -C /src --strip-components=1 && cp -r /src/apps/mcp /mcp
WORKDIR /mcp
RUN npm pkg delete devDependencies.@plunk/typescript-config \\
 && npm install --no-audit --no-fund \\
 && mkdir -p node_modules/@plunk \\
 && cp -r /src/packages/typescript-config node_modules/@plunk/typescript-config \\
 && npx tsc \\
 && npm pack --pack-destination /tmp

FROM node:22-alpine
WORKDIR /app
COPY --from=build /tmp/plunk-mcp-*.tgz /tmp/
RUN npm install --omit=dev --no-audit --no-fund /tmp/plunk-mcp-*.tgz """ + SDK + """ && npm ls && rm /tmp/plunk-mcp-*.tgz
""" + SERVER
else:
    assert re.fullmatch(r'[0-9]+\.[0-9]+\.[0-9]+', args.npm), 'la versión de npm es como 0.18.0'
    dockerfile = """# syntax=docker/dockerfile:1
FROM node:22-alpine
WORKDIR /app
RUN npm install --omit=dev --no-audit --no-fund @plunk/mcp@""" + args.npm + """ """ + SDK + """ && npm ls
""" + SERVER

assert '$' not in dockerfile, 'el Dockerfile no puede llevar $: Compose lo interpretaría como variable'
head = open('compose.head.yml').read()
tail = open('compose.tail.yml').read()
open(args.salida, 'w').write(head + ind(dockerfile, 8) + tail)
