# Genera docker-compose.yml con server.mjs incrustado en el Dockerfile (Dokploy raw no tiene repositorio)
#
#   python3 gen_compose.py                          # Plunk oficial: @plunk/mcp de npm
#   python3 gen_compose.py --plunk-lite <commit>    # Plunk Lite: el MCP del fork, en ese commit
#
# Con Plunk Lite, el commit es el de la imagen desplegada (scripts/plunk_lite_latest.py lo imprime).
# Así el MCP conoce las funciones que esa API tiene y no pide ninguna que le falte.
import argparse
import re
import textwrap

p = argparse.ArgumentParser(description='Genera el compose de plunk-mcp')
p.add_argument('salida', nargs='?', default='docker-compose.yml')
p.add_argument('--plunk-lite', metavar='COMMIT', help='compila el MCP de Plunk Lite en este commit')
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

if args.plunk_lite:
    assert re.fullmatch(r'[0-9a-f]{7,40}', args.plunk_lite), 'el commit es un hash, como el que da plunk_lite_latest.py'
    # Fase de compilación: solo apps/mcp y la config de TypeScript que extiende. apps/mcp se saca del
    # monorepo porque, dentro, npm intenta instalar los workspaces de la raíz. El paquete
    # @plunk/typescript-config no está en npm, así que se quita de devDependencies y se copia a mano.
    dockerfile = """# syntax=docker/dockerfile:1
FROM node:22-alpine AS build
ADD https://github.com/joanproductivo/plunk-lite/archive/""" + args.plunk_lite + """.tar.gz /tmp/src.tar.gz
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
    dockerfile = """# syntax=docker/dockerfile:1
FROM node:22-alpine
WORKDIR /app
RUN npm install --omit=dev --no-audit --no-fund @plunk/mcp@0.17.0 """ + SDK + """ && npm ls
""" + SERVER

assert '$' not in dockerfile, 'el Dockerfile no puede llevar $: Compose lo interpretaría como variable'
head = open('compose.head.yml').read()
tail = open('compose.tail.yml').read()
open(args.salida, 'w').write(head + ind(dockerfile, 8) + tail)
