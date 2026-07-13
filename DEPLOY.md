# Publicar o Radar do Eleitor na web (Streamlit Community Cloud — gratuito)

Com isso, qualquer eleitor acessa o painel por um link, sem instalar nada.

## Antes de começar — segurança

- **NUNCA** suba para o GitHub: `.env`, `config/secrets_local.py`, `database/*.db`.
  Já estão no `.gitignore` — confira com `git status` antes do primeiro push.
- A chave do Portal da Transparência vai nos **Secrets** do Streamlit Cloud
  (passo 4), nunca no código.

## Passo a passo

### 1. Criar o repositório no GitHub

1. Crie uma conta em https://github.com (se ainda não tiver).
2. Crie um repositório novo (pode ser privado): ex. `radar-do-eleitor`.
3. No PowerShell, dentro de `D:\radar-eleitoral-ia`:

```powershell
git init
git add .
git status   # CONFIRA: .env e secrets_local.py NÃO devem aparecer
git commit -m "Radar do Eleitor - primeira versao"
git branch -M main
git remote add origin https://github.com/SEU_USUARIO/radar-do-eleitor.git
git push -u origin main
```

### 2. Criar conta no Streamlit Community Cloud

1. Acesse https://share.streamlit.io e entre com a conta do GitHub.
2. Autorize o acesso ao repositório.

### 3. Criar o app

1. Clique em **New app**.
2. Repositório: `SEU_USUARIO/radar-do-eleitor` • Branch: `main`.
3. **Main file path**: `app_eleitor.py`.
4. Clique em **Deploy**.

### 4. Configurar a chave da API (Secrets)

1. No painel do app: **Settings → Secrets**.
2. Cole exatamente:

```toml
PORTAL_TRANSPARENCIA_API_KEY = "a36d908f650c6e0e3085694feb158c86"
```

3. Salve. O app reinicia sozinho e a seção de emendas passa a funcionar.
   (O `app_eleitor.py` já lê essa chave de `st.secrets` automaticamente.)

### 5. Testar

- Abra o link público gerado (algo como `https://radar-do-eleitor.streamlit.app`).
- Teste: buscar um deputado, um senador, trocar o ano, abrir as notas fiscais.

## Observações

- **Plano gratuito**: o app "hiberna" sem uso e acorda no primeiro acesso
  (demora ~30s). Limite de recursos é suficiente para este painel, pois os
  dados vêm das APIs oficiais e ficam em cache de 1 hora.
- **Atualizações**: basta `git add . && git commit -m "..." && git push` —
  o Streamlit Cloud redeploya sozinho.
- **Domínio próprio** (ex.: radardoeleitor.com.br): registre o domínio e
  aponte via CNAME nas configurações do app (recurso do Streamlit Cloud).
