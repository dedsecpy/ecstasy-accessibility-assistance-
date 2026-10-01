#!/bin/bash
# First-boot setup for an Amazon Linux 2023 EC2 instance: Docker, Compose, swap, clone, start.
# Paste into EC2 "Advanced details > User data":
#   #!/bin/bash
#   curl -fsSL https://raw.githubusercontent.com/dedsecpy/ecstasy-accessibility-assistance-/main/infra/aws/user-data.sh | bash
# Progress log on the server: /var/log/ecstasy-setup.log
exec > >(tee -a /var/log/ecstasy-setup.log) 2>&1
set -euxo pipefail

REPO=https://github.com/dedsecpy/ecstasy-accessibility-assistance-.git
DIR=/opt/ecstasy

dnf install -y docker git
systemctl enable --now docker
usermod -aG docker ec2-user

case "$(uname -m)" in
  x86_64) arch=x86_64; barch=amd64 ;;
  aarch64) arch=aarch64; barch=arm64 ;;
esac
plugins=/usr/local/lib/docker/cli-plugins
mkdir -p "$plugins"
curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-$arch" -o "$plugins/docker-compose"
bx=$(basename "$(curl -fsSL -o /dev/null -w '%{url_effective}' https://github.com/docker/buildx/releases/latest)")
curl -fsSL "https://github.com/docker/buildx/releases/download/$bx/buildx-$bx.linux-$barch" -o "$plugins/docker-buildx"
chmod +x "$plugins/docker-compose" "$plugins/docker-buildx"

# The Next.js build and Chroma need more memory than small instances have.
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo '/swapfile swap swap defaults 0 0' >> /etc/fstab
fi

[ -d "$DIR/.git" ] || git clone "$REPO" "$DIR"
chmod +x "$DIR/infra/aws/deploy.sh"
"$DIR/infra/aws/deploy.sh"
