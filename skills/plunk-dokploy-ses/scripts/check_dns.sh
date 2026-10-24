#!/usr/bin/env bash
# Comprueba los registros DNS que Plunk pide para un dominio de envío de AWS SES.
# Pregunta a los servidores autoritativos de la zona y a 1.1.1.1 y 8.8.8.8.
#
# Uso:
#   check_dns.sh <dominio_de_envio> <region> <token1> <token2> <token3> [subdominio_mail_from]
# Ejemplo:
#   check_dns.sh news.example.com eu-north-1 abc123 def456 ghi789
#
# Los tokens DKIM salen en el panel de Plunk (Settings -> Domains) o en ses_check.snippet.py.
# Sale con código 0 solo si los 5 registros obligatorios están bien en todos los servidores.

set -u
if [ $# -lt 5 ]; then
  sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'
  exit 2
fi
domain=${1%.}
region=$2
tokens="$3 $4 $5"
mailfrom="${6:-plunk}.$domain"

# Zona: el primer nombre, subiendo desde el dominio, que tenga registros NS propios
zone=$domain
ns=""
while [ -n "$zone" ]; do
  ns=$(dig +short NS "$zone" | sed 's/\.$//' | sort)
  [ -n "$ns" ] && break
  case $zone in *.*) zone=${zone#*.} ;; *) zone="" ;; esac
done
if [ -z "$ns" ]; then
  echo "No encuentro los servidores DNS de $domain"
  exit 2
fi
echo "Zona: $zone (los registros se crean en esta zona de tu proveedor DNS)"
echo "Autoritativos: $(echo $ns | tr '\n' ' ')"
rel=${domain%"$zone"}; rel=${rel%.}
if [ -n "$rel" ]; then
  echo "Nombres en el panel DNS: <token>._domainkey.$rel y ${6:-plunk}.$rel"
fi
echo

servers="$ns 1.1.1.1 8.8.8.8"
total=0
ok=0
check() { # descripción, valor obtenido, valor esperado
  total=$((total + 1))
  if [ "$2" = "$3" ]; then ok=$((ok + 1)); echo "  OK    $1"; else echo "  MAL   $1 -> [${2:-vacío}] (esperado: $3)"; fi
}

for s in $servers; do
  echo "@$s"
  for t in $tokens; do
    v=$(dig +short CNAME "$t._domainkey.$domain" @"$s" | head -1)
    check "CNAME ${t:0:8}…._domainkey" "$v" "$t.dkim.amazonses.com."
  done
  v=$(dig +short MX "$mailfrom" @"$s" | head -1)
  check "MX $mailfrom" "$v" "10 feedback-smtp.$region.amazonses.com."
  v=$(dig +short TXT "$mailfrom" @"$s" | tr -d '"' | grep -m1 'v=spf1')
  check "TXT $mailfrom" "$v" "v=spf1 include:amazonses.com ~all"
done

echo
echo "Avisos (no cuentan para el resultado):"
inbound=$(dig +short MX "$domain" | grep -i 'inbound-smtp' || true)
[ -n "$inbound" ] && echo "  - $domain tiene un MX a $inbound: es el registro opcional de \"inbound email\". Sin reglas de recepción en SES, el correo que llegue ahí se pierde. Bórralo salvo que lo hayas configurado a propósito."
dmarc=$(dig +short TXT "_dmarc.$zone" | tr -d '"' | grep -m1 'v=DMARC1' || true)
if [ -z "$dmarc" ]; then
  echo "  - $zone no publica DMARC. Gmail y Yahoo lo exigen para envíos masivos: añade TXT _dmarc con v=DMARC1; p=none;"
else
  echo "  - DMARC de $zone: $dmarc"
  case $dmarc in *p=reject*|*p=quarantine*) echo "    Con esa política, no envíes hasta que SES marque DKIM como SUCCESS." ;; esac
fi

echo
echo "Resultado: $ok/$total"
[ "$ok" -eq "$total" ]
