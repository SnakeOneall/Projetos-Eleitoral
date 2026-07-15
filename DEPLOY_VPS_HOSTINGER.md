# Deploy do Radar do Eleitor no VPS da Hostinger (KVM / Ubuntu)

Guia completo para rodar o Painel do Eleitor (Streamlit) num VPS KVM da
Hostinger, com domínio próprio e HTTPS. Assume **Ubuntu 22.04/24.04**.

Ao final você terá: `https://seudominio.cloud` servindo o app, rodando como
serviço (reinicia sozinho se cair ou se o servidor reiniciar).

Arquitetura:

    Internet → nginx (porta 443, HTTPS) → Streamlit (porta 8501, interno)

---

## 0. Antes de começar

- Contrate o plano **VPS KVM** e escolha **Ubuntu** na criação (painel hPanel
  da Hostinger → VPS → sistema operacional).
- Anote o **IP do VPS** e a **senha root** (ou configure chave SSH).
- No painel do domínio grátis (.cloud/.tech), aponte um registro **A**:
  - Tipo: `A` • Nome: `@` • Valor: `IP_DO_VPS`
  - (e outro `A` com Nome `www` → mesmo IP)
  - A propagação leva de minutos a algumas horas.

---

## 1. Acessar o servidor e atualizar

No seu PC (PowerShell ou terminal):

```bash
ssh root@IP_DO_VPS
```

Já dentro do servidor:

```bash
apt update && apt upgrade -y
apt install -y python3 python3-venv python3-pip git nginx ufw
```

Firewall básico (libera SSH e web):

```bash
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable
```

---

## 2. Baixar o projeto

```bash
cd /opt
git clone https://github.com/SnakeOneall/Projetos-Eleitoral.git radar
cd radar
python3 -m venv .venv
./.venv/bin/pip install --upgrade pip
./.venv/bin/pip install -r requirements.txt
```

> Os arquivos compactos do ETL (`data/processed/cmsp_*.csv.gz`) já vêm no
> repositório se você os commitou — então o app já sobe rápido, sem baixar
> nada pesado. Se quiser regenerá-los no servidor:
> `./.venv/bin/python scripts/etl_cmsp.py`

---

## 3. Configurar a chave da API (Portal da Transparência)

A chave entra como variável de ambiente do serviço (passo 4). Não precisa
de arquivo `.env` no servidor.

---

## 4. Criar o serviço (systemd) para o Streamlit

Crie o arquivo do serviço:

```bash
nano /etc/systemd/system/radar.service
```

Cole (ajuste nada além do necessário):

```ini
[Unit]
Description=Radar do Eleitor (Streamlit)
After=network.target

[Service]
User=root
WorkingDirectory=/opt/radar
Environment=PORTAL_TRANSPARENCIA_API_KEY=a36d908f650c6e0e3085694feb158c86
ExecStart=/opt/radar/.venv/bin/streamlit run app_eleitor.py \
  --server.port 8501 \
  --server.address 127.0.0.1 \
  --server.headless true \
  --server.enableCORS false \
  --server.enableXsrfProtection false
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Salve (Ctrl+O, Enter, Ctrl+X) e ative:

```bash
systemctl daemon-reload
systemctl enable radar
systemctl start radar
systemctl status radar     # deve mostrar "active (running)"
```

Teste local (opcional): `curl -I http://127.0.0.1:8501` deve responder 200.

---

## 5. Nginx como proxy reverso (com WebSocket)

O Streamlit usa WebSocket — o nginx precisa dos headers de upgrade.

```bash
nano /etc/nginx/sites-available/radar
```

Cole (troque `seudominio.cloud` pelo seu domínio):

```nginx
server {
    listen 80;
    server_name seudominio.cloud www.seudominio.cloud;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket (essencial para o Streamlit)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

Ative e recarregue:

```bash
ln -s /etc/nginx/sites-available/radar /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
nginx -t          # deve dizer "syntax is ok"
systemctl reload nginx
```

Agora `http://seudominio.cloud` já deve abrir o app (depois do DNS propagar).

---

## 6. HTTPS grátis (Let's Encrypt)

```bash
apt install -y certbot python3-certbot-nginx
certbot --nginx -d seudominio.cloud -d www.seudominio.cloud
```

Siga as perguntas (informe um e-mail, aceite os termos, escolha redirecionar
HTTP → HTTPS). O certbot ajusta o nginx sozinho e renova o certificado
automaticamente. Pronto: `https://seudominio.cloud`.

---

## 7. Atualizar o app depois (nova versão)

Sempre que você fizer `git push` de mudanças:

```bash
cd /opt/radar
git pull
./.venv/bin/pip install -r requirements.txt   # se mudaram dependências
systemctl restart radar
```

## 8. Atualizar os dados da CMSP (ETL periódico)

Para manter votações/presença/gastos recentes:

```bash
cd /opt/radar
./.venv/bin/python scripts/etl_cmsp.py
systemctl restart radar
```

Para automatizar toda segunda às 4h, edite o cron (`crontab -e`) e adicione:

```
0 4 * * 1 cd /opt/radar && ./.venv/bin/python scripts/etl_cmsp.py && systemctl restart radar
```

---

## Diagnóstico rápido

- Ver logs do app: `journalctl -u radar -n 100 --no-pager`
- Reiniciar o app: `systemctl restart radar`
- Ver logs do nginx: `tail -n 50 /var/log/nginx/error.log`
- App não abre: confira `systemctl status radar` e se o DNS (registro A)
  aponta para o IP do VPS.

---

## Segurança (recomendado)

- Crie um usuário não-root e use chave SSH em vez de senha.
- Mantenha o sistema atualizado: `apt update && apt upgrade -y`.
- A chave da API fica só no arquivo do serviço (permissão restrita); nunca a
  coloque em arquivo versionado.
