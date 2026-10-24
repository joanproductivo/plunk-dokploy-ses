# Genera docker-compose.yml con server.mjs incrustado en el Dockerfile (Dokploy raw no tiene repositorio)
import textwrap, sys
srv = open('server.mjs').read()
assert '$' not in srv, 'server.mjs no puede llevar $: Compose lo interpretaría como variable'
ind = lambda s, n: textwrap.indent(s, ' ' * n)
dockerfile = """# syntax=docker/dockerfile:1
FROM node:22-alpine
WORKDIR /app
RUN npm install --omit=dev --no-audit --no-fund @plunk/mcp@0.17.0 @modelcontextprotocol/server@2.4.0 @modelcontextprotocol/node@2.1.2 && npm ls
RUN cat > /app/server.mjs <<'EOF'
""" + srv + """EOF
USER node
ENV NODE_ENV=production PORT=3000
CMD ["node", "/app/server.mjs"]
"""
head = open('compose.head.yml').read()
tail = open('compose.tail.yml').read()
open(sys.argv[1] if len(sys.argv) > 1 else 'docker-compose.yml', 'w').write(head + ind(dockerfile, 8) + tail)
