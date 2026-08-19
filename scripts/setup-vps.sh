#!/usr/bin/env bash
# =============================================================================
# setup-vps.sh — prepara uma VM Ubuntu 24.04 ARM64 da Oracle Cloud
# =============================================================================
# Rode UMA VEZ, logo após criar a instância:
#
#   ssh ubuntu@SEU_IP
#   curl -fsSL https://raw.githubusercontent.com/SEU_USER/SEU_REPO/main/scripts/setup-vps.sh -o setup-vps.sh
#   chmod +x setup-vps.sh && ./setup-vps.sh
#
# O que faz: atualiza o sistema, instala Docker, CORRIGE O IPTABLES DA ORACLE
# (a pegadinha nº 1 do OCI), cria swap, endurece o SSH e habilita atualizações
# de segurança automáticas.
# =============================================================================

set -euo pipefail

log()  { echo -e "\n\033[1;34m==>\033[0m $*"; }
warn() { echo -e "\033[1;33m[!]\033[0m $*"; }

if [[ $EUID -eq 0 ]]; then
    echo "Não rode como root. Use o usuário 'ubuntu' — o script chama sudo quando precisa."
    exit 1
fi

# -----------------------------------------------------------------------------
log "1/7 — Atualizando o sistema"
sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get upgrade -y
sudo apt-get install -y ca-certificates curl gnupg git ufw fail2ban unattended-upgrades

# -----------------------------------------------------------------------------
log "2/7 — Instalando Docker Engine (ARM64)"
if ! command -v docker &>/dev/null; then
    sudo install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    sudo chmod a+r /etc/apt/keyrings/docker.gpg

    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    sudo apt-get update
    sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
                            docker-buildx-plugin docker-compose-plugin
    sudo usermod -aG docker "$USER"
    warn "Você foi adicionado ao grupo docker. Saia e entre de novo no SSH para valer."
else
    echo "Docker já instalado: $(docker --version)"
fi

# -----------------------------------------------------------------------------
log "3/7 — Corrigindo o firewall (a pegadinha do Oracle Cloud)"
# As imagens Ubuntu da Oracle vêm com regras iptables que DESCARTAM tudo que
# não seja SSH. Abrir a porta na Security List do console NÃO basta: se este
# passo for pulado, o Let's Encrypt falha e o webhook do Telegram nunca chega,
# sem nenhuma mensagem de erro óbvia.
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p udp --dport 443 -j ACCEPT

# Persistir as regras entre reinicializações.
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent
sudo netfilter-persistent save

echo "Regras INPUT ativas:"
sudo iptables -L INPUT -n --line-numbers | head -20

# -----------------------------------------------------------------------------
log "4/7 — Criando swap de 4 GB"
# 12 GB de RAM sobram para esta stack, mas o swap evita que um pico de build
# do Docker mate o processo por OOM.
if ! sudo swapon --show | grep -q '/swapfile'; then
    sudo fallocate -l 4G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
    sudo sysctl -p /etc/sysctl.d/99-swappiness.conf
else
    echo "Swap já configurado."
fi

# -----------------------------------------------------------------------------
log "5/7 — Endurecendo o SSH"
# A imagem da Oracle já vem sem login por senha, mas confirmamos.
sudo sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/'   /etc/ssh/sshd_config
sudo sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin no/'                 /etc/ssh/sshd_config
sudo systemctl restart ssh || sudo systemctl restart sshd

# fail2ban contra força bruta no SSH
sudo systemctl enable --now fail2ban

# -----------------------------------------------------------------------------
log "6/7 — Habilitando atualizações de segurança automáticas"
sudo dpkg-reconfigure -f noninteractive unattended-upgrades

# -----------------------------------------------------------------------------
log "7/7 — Ajustando fuso e limpando"
sudo timedatectl set-timezone UTC     # servidor em UTC; a app converte por usuário
sudo apt-get autoremove -y

log "Pronto."
cat <<'EOF'

Próximos passos:
  1. Saia e reconecte o SSH (para o grupo docker valer):   exit
  2. Confirme:                                             docker run --rm hello-world
  3. Clone o repositório e configure o .env
  4. Suba a stack:                                         ./scripts/deploy.sh

Verifique também no console da Oracle:
  Networking → VCN → Security List → Ingress Rules
  0.0.0.0/0 → TCP 80 e TCP 443 precisam estar liberados.

EOF
