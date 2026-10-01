#!/usr/bin/env bash
# Pull the latest code from GitHub and (re)start the full stack behind Caddy.
# On the server:  sudo /opt/ecstasy/infra/aws/deploy.sh
# Own domain:     sudo SITE_ADDRESS=app.example.com /opt/ecstasy/infra/aws/deploy.sh
#                 (remembered in .site-address; the sslip.io link keeps working alongside it)
set -euo pipefail
cd "$(dirname "$0")/../.."

git pull --ff-only
[ -f .env ] || cp .env.example .env

if [ -n "${SITE_ADDRESS:-}" ]; then
  echo "$SITE_ADDRESS" > .site-address
elif [ -s .site-address ]; then
  SITE_ADDRESS=$(cat .site-address)
fi

token=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
ip=$(curl -fsS -H "X-aws-ec2-metadata-token: $token" http://169.254.169.254/latest/meta-data/public-ipv4)
SSLIP="${ip//./-}.sslip.io"
export SITE_ADDRESS="${SITE_ADDRESS:+$SITE_ADDRESS, }$SSLIP"

docker compose -f infra/docker-compose.yml -f infra/docker-compose.aws.yml up -d --build --remove-orphans
docker image prune -f >/dev/null

echo
echo "Ecstasy is starting at: ${SITE_ADDRESS//, / and }"
echo "First start takes a minute or two while the worker seeds and indexes the venue."
