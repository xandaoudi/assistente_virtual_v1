# Guia de Deployment — Oracle Cloud Infrastructure (Always Free)

**Projeto:** `assistente_virtual_v1`
**Alvo:** VM Ampere A1 (ARM64), Ubuntu 24.04 LTS, Docker Compose
**Versão:** 0.1 · 18/08/2026

---

## 0. Antes de começar: leia isto

Três fatos sobre o Oracle Cloud que economizam horas de frustração:

1. **O Always Free encolheu em 2026.** O Ampere A1 caiu de 4 OCPU / 24 GB para **2 OCPU / 12 GB** (1.500 OCPU-horas e 9.000 GB-horas por mês). A Oracle fez a mudança sem anúncio público. Ainda é folgado para este projeto, mas dimensione com o número novo.

2. **"Out of host capacity" é a regra, não a exceção.** As regiões populares vivem sem capacidade A1. A seção §2.3 traz três formas de contornar.

3. **Abrir a porta no console não abre a porta.** As imagens Ubuntu da Oracle vêm com regras `iptables` que descartam tudo que não seja SSH. Você precisa liberar nos **dois** lugares: Security List (console) **e** iptables (dentro da VM). Esta é, de longe, a causa nº 1 de "meu site não abre e não sei por quê".

**Recursos Always Free relevantes** (limites atuais):

| Recurso | Cota |
|---|---|
| Ampere A1 (ARM) | 2 OCPU + 12 GB RAM |
| VM.Standard.E2.1.Micro (x86) | 2 instâncias, 1/8 OCPU + 1 GB cada |
| Block storage | 200 GB no total (boot mínimo 47 GB) |
| Tráfego de saída | 10 TB/mês |
| Object Storage | 10 GB (útil para backups off-site) |
| Load balancer flexível | 1 (10 Mbps) — **não precisamos**, o Caddy resolve |

---

## 1. Arquitetura do deployment

```
                          Internet
                              │
                    ┌─────────▼─────────┐
                    │  Oracle VCN       │
                    │  Security List:   │  ← camada 1 de firewall
                    │  22, 80, 443      │
                    └─────────┬─────────┘
                              │
    ╔═════════════════════════▼══════════════════════════════╗
    ║  VM Ampere A1 · Ubuntu 24.04 ARM64 · 2 OCPU / 12 GB     ║
    ║                                                          ║
    ║   iptables (camada 2 de firewall)                        ║
    ║              │                                           ║
    ║   ┌──────────▼──────────┐                                ║
    ║   │  caddy  :80 :443    │  HTTPS automático              ║
    ║   └──────────┬──────────┘  (Let's Encrypt)               ║
    ║              │  rede docker "frontend"                   ║
    ║   ┌──────────▼──────────┐   ┌──────────────────┐         ║
    ║   │  api  (FastAPI)     │   │  scheduler       │         ║
    ║   │  2 workers  :8000   │   │  (APScheduler)   │         ║
    ║   └──────────┬──────────┘   └────────┬─────────┘         ║
    ║              │  rede docker "backend" (internal)         ║
    ║   ┌──────────▼───────────────────────▼─────────┐         ║
    ║   │  db — PostgreSQL 16   (sem porta exposta)  │         ║
    ║   └────────────────────────────────────────────┘         ║
    ║                                                          ║
    ║   Volumes: pgdata · media · caddy_data                    ║
    ╚══════════════════════════════════════════════════════════╝
```

**Orçamento de memória** (12 GB disponíveis):

| Serviço | Limite | Uso típico |
|---|---|---|
| PostgreSQL | 3 GB | ~300 MB |
| API (2 workers) | 3 GB | ~600 MB |
| Scheduler | 1 GB | ~200 MB |
| Caddy | — | ~50 MB |
| Sistema + Docker | — | ~800 MB |
| **Folga** | | **~7 GB** |

Sobra espaço confortável. Guarde essa folga — é ela que permite subir um Ollama pequeno na Fase 4 sem trocar de máquina (com ressalvas, §11).

---

## 2. Criar a instância

### 2.1 Conta

1. Crie a conta em [oracle.com/cloud/free](https://www.oracle.com/cloud/free/). Exige cartão de crédito para verificação (cobra ~US$ 1 e estorna).
2. **Escolha a região com cuidado** — ela é permanente para a home region. `sa-saopaulo-1` ou `sa-vinhedo-1` dão a menor latência para o Brasil, mas costumam ter mais disputa por capacidade A1.
3. Termine no modo **Always Free**. Se um dia migrar para PAYG, os recursos Always Free continuam gratuitos — e o problema de capacidade praticamente some.

### 2.2 Criar a VM

No console: **Compute → Instances → Create Instance**

| Campo | Valor |
|---|---|
| Name | `assistente-virtual` |
| Image | **Canonical Ubuntu 24.04** (confira que é a build ARM/aarch64) |
| Shape | **VM.Standard.A1.Flex** |
| OCPUs | **2** |
| Memory | **12 GB** |
| Boot volume | **100 GB** (dentro dos 200 GB gratuitos; o padrão de 50 GB fica apertado com imagens Docker) |
| VCN | Criar nova, com subnet **pública** |
| Public IP | **Assign** |
| SSH keys | Faça upload da sua chave pública |

Gere a chave, se ainda não tiver:

```bash
ssh-keygen -t ed25519 -C "oracle-assistente" -f ~/.ssh/oracle_assistente
# a chave pública a subir é ~/.ssh/oracle_assistente.pub
```

> **Boot volume de 100 GB:** o `Boot volume performance` deve ficar em **Balanced**. O padrão "Lower cost" entrega ~10 VPU e deixa o build de imagens Docker bem lento.

### 2.3 Quando aparecer "Out of host capacity"

Erro esperado. Três saídas, da mais simples à mais confiável:

**A. Trocar de Availability Domain.** Em regiões com AD-1, AD-2 e AD-3, tente os três. Leva 30 segundos e às vezes resolve.

**B. Insistir por script.** A capacidade é liberada em janelas curtas. Instale a [OCI CLI](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm) e rode um laço de tentativa a cada poucos minutos:

```bash
while true; do
  oci compute instance launch --from-json file://instance.json \
    && { echo "Criada!"; break; }
  echo "$(date '+%H:%M:%S') sem capacidade — nova tentativa em 3 min"
  sleep 180
done
```

Gere o `instance.json` uma vez pelo console (o botão **Save as stack / Copy as CLI command** na tela de criação já monta o payload). Existem projetos prontos que fazem isso, como [`oci-instance-creator`](https://github.com/mowirth/oci-instance-creator).

**C. Migrar para Pay-As-You-Go.** É o caminho pragmático: a conta passa a ter prioridade de alocação, os recursos Always Free continuam gratuitos, e você só paga se estourar as cotas. Configure um **budget alert** em US$ 1 para não ter surpresa.

**Plano B enquanto isso:** suba primeiro em duas E2.1.Micro (x86, sempre disponíveis) — uma para app, outra para banco. É apertado, mas destrava o desenvolvimento, e o `docker-compose.yml` deste repositório funciona nas duas arquiteturas.

### 2.4 Abrir as portas na Security List

**Networking → Virtual Cloud Networks → sua VCN → Security Lists → Default Security List → Add Ingress Rules**

| Stateless | Source CIDR | Protocolo | Porta destino | Descrição |
|---|---|---|---|---|
| No | `0.0.0.0/0` | TCP | 80 | HTTP (validação do Let's Encrypt) |
| No | `0.0.0.0/0` | TCP | 443 | HTTPS |
| No | `0.0.0.0/0` | UDP | 443 | HTTP/3 (opcional) |

A regra de SSH (22) já vem por padrão. **Restrinja-a ao seu IP** se ele for fixo.

> Note que a porta **5432 não aparece nesta lista**. O Postgres nunca deve estar acessível pela internet. Para acessá-lo do seu computador, use túnel SSH (§9.2).

---

## 3. Preparar o servidor

Conecte:

```bash
ssh -i ~/.ssh/oracle_assistente ubuntu@SEU_IP_PUBLICO
```

Rode o script de preparação (está em `scripts/setup-vps.sh` neste repositório):

```bash
curl -fsSL https://raw.githubusercontent.com/SEU_USER/assistente_virtual_v1/main/scripts/setup-vps.sh -o setup-vps.sh
chmod +x setup-vps.sh
./setup-vps.sh
exit          # necessário: o grupo docker só vale na próxima sessão
```

Ele executa, em ordem: atualização do sistema → Docker Engine ARM64 → **correção do iptables** → swap de 4 GB → hardening do SSH + fail2ban → unattended-upgrades → timezone UTC.

### 3.1 A correção do iptables, em detalhe

Se você preferir fazer à mão, é isto:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p udp --dport 443 -j ACCEPT

sudo apt-get install -y iptables-persistent
sudo netfilter-persistent save        # sem isto, some no reboot
```

O `-I INPUT 6` insere **antes** da regra `REJECT` que a Oracle coloca no fim da cadeia. Adicionar com `-A` (append) coloca depois do REJECT e não tem efeito nenhum — erro comum e silencioso.

Confira:

```bash
sudo iptables -L INPUT -n --line-numbers
```

As regras de ACCEPT para 80/443 precisam aparecer **acima** de qualquer `REJECT` ou `DROP`.

> **Não use `ufw` nesta VM** junto com o iptables da Oracle. O `ufw` reescreve as cadeias e, dependendo da ordem, derruba seu próprio SSH. Se quiser usar `ufw`, limpe as regras da Oracle primeiro e assuma todo o controle por ele.

---

## 4. Domínio e HTTPS — opções gratuitas

O webhook do Telegram **exige HTTPS com certificado válido**. IP puro não serve. Três caminhos, todos com custo zero.

### Comparação

| | **A. DuckDNS + Caddy** | **B. Cloudflare Tunnel** | **C. Domínio próprio + Caddy** |
|---|---|---|---|
| Custo | Zero | Zero | ~R$ 40/ano (o domínio) |
| Precisa domínio? | Não | **Sim** (e o DNS tem que ir para a Cloudflare) | Sim |
| Abre portas na VM? | Sim (80/443) | **Não** | Sim |
| Expõe o IP da VM? | Sim | Não | Sim (a menos que use proxy CF) |
| Certificado | Let's Encrypt automático | Cloudflare, automático | Let's Encrypt automático |
| Passos extras | Nenhum | Instalar `cloudflared` | Apontar DNS |
| Cara de produção? | Não (`.duckdns.org`) | Sim | Sim |
| **Melhor para** | **MVP, começar hoje** | Rede travada / paranoia com portas | Fase 2 em diante |

**Recomendação:** comece com **A**. Migrar para C depois é trocar uma variável no `.env` e um registro DNS — o Caddy reemite o certificado sozinho.

Se o iptables da Oracle estiver te vencendo, **B** contorna o problema inteiro (o `cloudflared` abre uma conexão *de dentro para fora*, então nada precisa ser aberto). O preço é ter que mover o DNS do seu domínio para a Cloudflare — o que exige já ter um domínio.

### 4.1 Opção A — DuckDNS (recomendada para o MVP)

1. Entre em [duckdns.org](https://www.duckdns.org) e faça login (GitHub, Google etc.).
2. Crie um subdomínio, ex.: `assistente-alexandre`. Você fica com `assistente-alexandre.duckdns.org`.
3. Coloque o IP público da VM no campo **current ip** e clique em **update ip**.
4. Anote o **token** que aparece no topo da página.

Confirme a resolução:

```bash
dig +short assistente-alexandre.duckdns.org      # deve devolver o IP da VM
```

Como o IP público da Oracle é reservado e não muda, você não precisa de um atualizador rodando. Mas é barato deixar um por segurança:

```bash
mkdir -p ~/duckdns
cat > ~/duckdns/duck.sh <<'EOF'
#!/bin/bash
curl -fsS "https://www.duckdns.org/update?domains=SEU_SUBDOMINIO&token=SEU_TOKEN&ip=" \
  -o ~/duckdns/duck.log
EOF
chmod 700 ~/duckdns/duck.sh
(crontab -l 2>/dev/null; echo "*/30 * * * * ~/duckdns/duck.sh >/dev/null 2>&1") | crontab -
```

Depois é só preencher no `.env`:

```
APP_DOMAIN=assistente-alexandre.duckdns.org
ACME_EMAIL=seu-email@exemplo.com
```

O Caddy cuida do resto: pede o certificado ao Let's Encrypt no primeiro start e renova sozinho para sempre.

### 4.2 Opção B — Cloudflare Tunnel (sem abrir portas)

Requer um domínio com o DNS gerenciado pela Cloudflare (plano gratuito serve).

```bash
# Instalar o cloudflared (ARM64)
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

cloudflared tunnel login                          # abre um link para autorizar
cloudflared tunnel create assistente
cloudflared tunnel route dns assistente assistente.seudominio.com
```

`~/.cloudflared/config.yml`:

```yaml
tunnel: assistente
credentials-file: /home/ubuntu/.cloudflared/<TUNNEL_ID>.json
ingress:
  - hostname: assistente.seudominio.com
    service: http://localhost:8000
  - service: http_status:404
```

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
```

Com o túnel, **remova o serviço `caddy` do compose** e exponha a API em `127.0.0.1:8000` (nunca `0.0.0.0`). As portas 80/443 continuam fechadas na Security List.

> Túneis "quick" (`trycloudflare.com`, sem login) geram uma URL aleatória que muda a cada reinício. Servem para testar o webhook por 10 minutos, não para produção.

### 4.3 Opção C — domínio próprio

Registre onde preferir (registro.br, Cloudflare Registrar, Namecheap), crie um registro **A** apontando para o IP da VM e ponha o domínio em `APP_DOMAIN`. Nada mais muda.

---

## 5. Subir a aplicação

```bash
ssh ubuntu@SEU_IP

git clone https://github.com/SEU_USER/assistente_virtual_v1.git
cd assistente_virtual_v1

cp .env.example .env
chmod 600 .env
nano .env               # preencha tudo (§5.1)

chmod +x scripts/*.sh
docker compose up -d --build

docker compose ps
docker compose logs -f caddy      # acompanhe a emissão do certificado
```

Se tudo deu certo, o log do Caddy mostra `certificate obtained successfully` em poucos segundos.

Teste:

```bash
curl -I https://SEU_DOMINIO/health      # esperado: HTTP/2 200
```

### 5.1 Gerando os segredos

```bash
echo "POSTGRES_PASSWORD=$(openssl rand -hex 32)"
echo "TELEGRAM_WEBHOOK_SECRET=$(openssl rand -hex 32)"
echo "WEBHOOK_SECRET_PATH=$(openssl rand -hex 24)"
docker run --rm python:3.12-slim sh -c \
  "pip install -q cryptography && python -c 'from cryptography.fernet import Fernet; print(\"ENCRYPTION_KEY=\"+Fernet.generate_key().decode())'"
```

> Guarde a `ENCRYPTION_KEY` fora do servidor também. Perdê-la significa perder o acesso a todos os refresh tokens do Google já salvos — os usuários teriam que reconectar o Google Calendar do zero.

### 5.2 Registrar o webhook do Telegram

O `deploy.sh` já faz isso, mas manualmente é:

```bash
source .env
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/setWebhook" \
  -d "url=https://${APP_DOMAIN}/webhook/${WEBHOOK_SECRET_PATH}" \
  -d "secret_token=${TELEGRAM_WEBHOOK_SECRET}" \
  -d "allowed_updates=[\"message\",\"callback_query\"]"

# Conferir estado
curl "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getWebhookInfo"
```

Em `getWebhookInfo`, o campo `last_error_message` é seu melhor amigo no diagnóstico. Se ele disser `SSL error` ou `connection refused`, o problema é rede/certificado, não a sua aplicação.

---

## 6. Atualizações do dia a dia

```bash
cd ~/assistente_virtual_v1
./scripts/deploy.sh
```

O script faz: backup → `git pull` → build → migrations → restart → healthcheck, e **faz rollback automático da imagem** se o healthcheck falhar.

> Uma ressalva honesta sobre o rollback: ele reverte o **código**, não as **migrations**. Uma migration destrutiva (`DROP COLUMN`) já terá sido aplicada. Por isso o backup roda antes de tudo. A prática segura é escrever migrations aditivas: adicione a coluna nova, faça o deploy, migre os dados, e só remova a antiga num deploy posterior.

### 6.1 Deploy automático via GitHub Actions (opcional)

Se quiser deploy a cada push na `main`, crie `.github/workflows/deploy.yml`:

```yaml
name: Deploy
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy via SSH
        uses: appleboy/ssh-action@v1
        with:
          host:     ${{ secrets.VPS_HOST }}
          username: ubuntu
          key:      ${{ secrets.VPS_SSH_KEY }}
          script: |
            cd ~/assistente_virtual_v1
            ./scripts/deploy.sh
```

Cadastre `VPS_HOST` e `VPS_SSH_KEY` em **Settings → Secrets and variables → Actions**. Use uma **chave SSH dedicada** para o CI, não a sua pessoal.

---

## 7. Observabilidade

### 7.1 Logs

```bash
docker compose logs -f api                 # aplicação
docker compose logs -f --tail=100 scheduler
docker compose logs -f caddy
```

Limite o tamanho dos logs para não encher o disco — crie `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
```

```bash
sudo systemctl restart docker
```

### 7.2 Monitoramento leve

```bash
docker stats --no-stream          # CPU e memória por container
df -h /                           # disco
free -h                           # RAM e swap
```

Um alerta simples de disco cheio via cron:

```bash
(crontab -l 2>/dev/null; echo '0 * * * * [ $(df / --output=pcent | tail -1 | tr -dc 0-9) -gt 85 ] && curl -s -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" -d chat_id=<SEU_CHAT_ID> -d text="Disco da VPS acima de 85%"') | crontab -
```

Para uptime externo, [UptimeRobot](https://uptimerobot.com) monitora `https://SEU_DOMINIO/health` a cada 5 minutos no plano gratuito — vale mais do que qualquer monitoramento interno, porque ele te avisa justamente quando a VM inteira caiu.

---

## 8. Backup e recuperação

### 8.1 Backup diário automático

```bash
crontab -e
```

```cron
# Backup do banco todo dia às 03:00 UTC (00:00 em São Paulo)
0 3 * * * cd /home/ubuntu/assistente_virtual_v1 && ./scripts/backup-db.sh >> /var/log/av-backup.log 2>&1
```

### 8.2 Cópia off-site (Object Storage, 10 GB gratuitos)

Um backup guardado na mesma VM não protege contra a perda da VM. Crie um bucket no console (**Storage → Buckets**), instale a OCI CLI e adicione ao `.env`:

```
OCI_BACKUP_BUCKET=assistente-backups
```

O `backup-db.sh` detecta a variável e envia automaticamente.

### 8.3 Restauração

```bash
./scripts/restore-db.sh backups/av_20260818_030000.sql.gz
```

**Teste isto agora, com dados de brinquedo.** Um backup nunca restaurado é uma suposição, não um backup.

### 8.4 Snapshot do boot volume

No console: **Storage → Block Volumes → seu boot volume → Create Backup**. A cota gratuita permite 5 backups de volume. Faça um antes de qualquer mudança grande de infraestrutura — restaura a VM inteira, não só o banco.

---

## 9. Segurança

Checklist alinhado aos RNF do `requirements.md`:

| Item | Status nesta configuração |
|---|---|
| Postgres sem porta pública | Sim — sem `ports:` e em rede `internal` |
| Segredos fora do git | Sim — `.env` no `.gitignore`, permissão 600 |
| Container sem root | Sim — usuário `app` (UID 1001) no Dockerfile |
| TLS obrigatório | Sim — Caddy redireciona HTTP→HTTPS automaticamente |
| HSTS e headers de segurança | Sim — no `Caddyfile` |
| Webhook autenticado | Sim — caminho secreto + header `X-Telegram-Bot-Api-Secret-Token` |
| SSH só com chave | Sim — `setup-vps.sh` desabilita senha e login root |
| Força bruta no SSH | Sim — `fail2ban` |
| Patches de segurança | Sim — `unattended-upgrades` |
| Refresh tokens cifrados | **Depende da aplicação** — use `ENCRYPTION_KEY` (RNF-03) |
| Rate limiting por usuário | **Depende da aplicação** — RNF-17 |

### 9.1 Restringir o SSH ao seu IP

Se seu IP residencial for estável, edite a regra de ingress da porta 22 trocando `0.0.0.0/0` por `SEU_IP/32`. É a melhoria de segurança com maior retorno por esforço aqui.

### 9.2 Acessar o banco do seu computador

Sem abrir a porta 5432:

```bash
ssh -L 5432:localhost:5432 ubuntu@SEU_IP -N
```

E aponte o DBeaver/pgAdmin para `localhost:5432`. Para isso funcionar, o container precisa publicar a porta apenas no loopback — adicione ao `db` um `ports: ["127.0.0.1:5432:5432"]` **temporariamente**, ou use:

```bash
docker compose exec db psql -U assistente -d assistente_virtual
```

que dispensa qualquer porta.

---

## 10. Diagnóstico de problemas

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `curl https://dominio` dá timeout | iptables bloqueando | `sudo iptables -L INPUT -n --line-numbers` — ACCEPT de 80/443 tem que vir antes do REJECT (§3.1) |
| Caddy não obtém certificado | Porta 80 fechada ou DNS errado | `dig +short SEU_DOMINIO` deve retornar o IP da VM; confira a Security List |
| `too many failed authorizations` | Cota do Let's Encrypt estourada | Ative `acme_ca` de staging no `Caddyfile`, corrija, depois volte para produção. A cota reseta em 1 h |
| Bot não responde | Webhook não registrado | `curl .../getWebhookInfo` e leia `last_error_message` |
| `connection refused` no webhook | API caiu | `docker compose ps` e `docker compose logs api` |
| Build do Docker muito lento | Boot volume "Lower cost" | Mude a performance do boot volume para **Balanced** |
| `exec format error` | Imagem x86 numa VM ARM | Verifique se a imagem base publica `linux/arm64`; se não, use `platform: linux/amd64` (roda emulado e lento) ou troque de imagem |
| OOM matando containers | Limite de memória baixo | `docker stats`; ajuste os `deploy.resources.limits` do compose |
| Disco cheio | Imagens e logs acumulados | `docker system prune -a --volumes` (**cuidado**: `--volumes` apaga dados; sem ele é seguro) |
| Perdi o acesso SSH | Regra de firewall errada | Console da Oracle → **Cloud Shell** → conecte pela rede interna, ou use a serial console da instância |

### 10.1 Comandos de verificação rápida

```bash
# A VM está ouvindo nas portas?
sudo ss -tlnp | grep -E ':(80|443)'

# O tráfego chega até a VM? (rode do seu computador)
nc -zv SEU_IP 443

# A API responde por dentro?
docker compose exec api curl -sS localhost:8000/health

# O Caddy consegue falar com a API?
docker compose exec caddy wget -qO- http://api:8000/health
```

---

## 11. Fase 4 — LLM local nesta VM

Vale um alerta antes de você contar com isso: **2 OCPU ARM e 12 GB de RAM rodam um modelo pequeno, mas devagar**.

| Modelo (quantizado Q4) | RAM | Velocidade estimada nesta VM | Function calling em PT-BR |
|---|---|---|---|
| Llama 3.2 3B | ~2,5 GB | ~8-12 tok/s | Fraco |
| Qwen 2.5 7B | ~5 GB | ~3-5 tok/s | Razoável |
| Llama 3.1 8B | ~5,5 GB | ~3-4 tok/s | Razoável |

Sem GPU, uma resposta de 200 tokens leva de 40 a 60 segundos. Para um bot conversacional, isso é inviável — o RNF-12 pede 5 s no p95.

Caminhos realistas para a Fase 4:

1. **Máquina separada com GPU** em casa, exposta via Cloudflare Tunnel, com a VPS da Oracle atuando só como gateway.
2. **Modelo pequeno para tarefas restritas** (classificar categoria, extrair valor) e LLM em nuvem para a conversa. Aproveita o melhor dos dois e reduz custo de API.
3. **Instância A10 GPU paga** na própria Oracle, ligada apenas quando necessário.

A boa notícia: como o RNF-08 exige a abstração de provider, testar qualquer uma dessas alternativas é mudar `LLM_PROVIDER` e `LLM_BASE_URL` no `.env`. Nenhuma linha da lógica de negócio muda.

---

## 12. Custos

**Cenário Always Free:** R$ 0,00 de infraestrutura.

O que realmente sai do bolso:

| Item | Custo estimado (mensal) |
|---|---|
| VPS Oracle Always Free | R$ 0 |
| Domínio DuckDNS | R$ 0 |
| Certificado (Let's Encrypt) | R$ 0 |
| Domínio próprio (opcional) | ~R$ 3,50 (R$ 40/ano) |
| **API de LLM** | **R$ 15 a R$ 80**, conforme uso e modelo |
| Object Storage (backups) | R$ 0 até 10 GB |

A API da LLM é o único custo significativo. Por isso o `TRACK_LLM_COST=true` e os limites do RNF-17 estão no `.env` desde o início: com um bot conversacional, o custo escala com o número de mensagens, não com o número de usuários — e uma conversa em loop pode gastar muito rápido.

**Configure um budget alert na Oracle mesmo estando no Always Free:** console → **Billing → Budgets**, alerta em US$ 1. Se você acidentalmente criar um recurso pago, quer descobrir no primeiro dólar, não no fim do mês.

---

## 13. Checklist de go-live

- [ ] Instância A1 criada e acessível por SSH
- [ ] `setup-vps.sh` executado sem erro
- [ ] Regras 80/443 na Security List **e** no iptables (`iptables -L INPUT -n`)
- [ ] Domínio resolvendo para o IP da VM (`dig +short`)
- [ ] `.env` preenchido, com permissão 600, e fora do git
- [ ] `docker compose ps` com todos os serviços em `healthy`
- [ ] `curl -I https://SEU_DOMINIO/health` retornando 200
- [ ] Certificado válido no navegador (cadeado)
- [ ] Webhook registrado e `getWebhookInfo` sem erro
- [ ] Bot responde a uma mensagem de teste no Telegram
- [ ] Backup automático no cron
- [ ] **Restauração testada** com `restore-db.sh`
- [ ] `ENCRYPTION_KEY` guardada fora do servidor
- [ ] Budget alert configurado na Oracle
- [ ] Monitoramento externo de uptime ativo
- [ ] Snapshot do boot volume criado

---

## 14. Arquivos deste repositório

| Arquivo | Papel |
|---|---|
| `docker-compose.yml` | Orquestração dos 4 serviços, redes e volumes |
| `Dockerfile` | Imagem multi-stage da aplicação (ARM64 e AMD64) |
| `.env.example` | Todas as variáveis, comentadas e ligadas aos requisitos |
| `deploy/Caddyfile` | Reverse proxy, HTTPS automático e headers de segurança |
| `scripts/setup-vps.sh` | Preparação da VM (rode uma vez) |
| `scripts/deploy.sh` | Deploy com backup, migrations e rollback |
| `scripts/backup-db.sh` | Dump com rotação e envio off-site |
| `scripts/restore-db.sh` | Restauração guiada |
| `.dockerignore` / `.gitignore` | Higiene de build e de segredos |

---

## Referências

- [Oracle — Always Free Resources (limites oficiais)](https://docs.oracle.com/en-us/iaas/Content/FreeTier/freetier_topic-Always_Free_Resources.htm)
- [InfoQ — Oracle reduz pela metade os limites do Ampere A1](https://www.infoq.com/news/2026/07/oracle-cloud-free-tier-limits/)
- [Linuxiac — corte silencioso no free tier](https://linuxiac.com/oracle-quietly-cuts-free-tier-ampere-a1-resources-in-half/)
- [Contornando o "Out of capacity" com a OCI CLI](https://hitrov.medium.com/resolving-oracle-cloud-out-of-capacity-issue-and-getting-free-vps-with-4-arm-cores-24gb-of-a3d7e6a027a8)
- [oci-instance-creator](https://github.com/mowirth/oci-instance-creator)
- [Cloudflare Tunnel — documentação](https://developers.cloudflare.com/tunnel/)
- [DuckDNS](https://www.duckdns.org)
