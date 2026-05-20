# LensShop — Google Ads MCP Server

Servidor MCP customizado para a conta Google Ads da LensShop, hospedado na VPS Hostinger.

---

## Arquitetura

```
[Claude Code / claude.ai]
        │
        │ MCP (streamable-http)
        ▼
https://ads-mcp.redeastrum.com.br  (nginx → porta 8090)
        │
        │ Application Default Credentials
        ▼
[Google Ads API]  conta: 5521940727
```

---

## VPS

- **IP:** `72.60.163.179`
- **OS:** Debian 13
- **Diretório do projeto:** `/root/google-ads-mcp`
- **Processo PM2:** `google-ads-mcp` (id 2)
- **Porta:** `8090`
- **URL pública:** `https://ads-mcp.redeastrum.com.br/mcp`

---

## Ferramentas disponíveis

| Ferramenta | Descrição |
|---|---|
| `search` | Consulta GAQL na API do Google Ads |
| `get_resource_metadata` | Lista campos disponíveis por recurso |
| `set_campaign_status` | Ativar / pausar campanha |
| `update_campaign_budget` | Alterar orçamento diário (BRL) |
| `set_campaign_target_roas` | Definir Target ROAS |
| `rename_campaign` | Renomear campanha |

---

## Variáveis de ambiente (`.env` em `/root/google-ads-mcp/`)

| Variável | Descrição |
|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | Caminho para `/root/.google/google_ads_credentials.json` |
| `GOOGLE_ADS_DEVELOPER_TOKEN` | Developer token da API |
| `GOOGLE_ADS_LOGIN_CUSTOMER_ID` | `5521940727` |
| `GOOGLE_ADS_MCP_HTTP_MODE` | `true` — habilita transporte HTTP sem OAuth por usuário |
| `GOOGLE_ADS_MCP_BASE_URL` | `https://ads-mcp.redeastrum.com.br` |
| `PORT` | `8090` |

O arquivo `/root/.google/google_ads_credentials.json` contém as credenciais `authorized_user`
(refresh token OAuth2) geradas localmente e copiadas para o servidor.

---

## Deploy automático

Qualquer push na branch `lensshop/mutate-tools` dispara o GitHub Actions (`.github/workflows/deploy.yml`),
que chama o webhook `https://lensconfig.redeastrum.com.br/ads-deploy`.

O webhook executa `/root/google-ads-mcp/deploy.sh`:
1. `git fetch` + `git reset --hard origin/lensshop/mutate-tools`
2. `pip install -e .` (atualiza dependências)
3. `pm2 restart google-ads-mcp`

**Secret do GitHub Actions:** `DEPLOY_WEBHOOK_SECRET` = `lensshop-deploy-secret-2026`
→ Configurar em: `github.com/gbmv33/google-ads-mcp-lensshop` → Settings → Secrets → Actions

---

## DNS (Cloudflare)

O domínio `redeastrum.com.br` usa Cloudflare como DNS.
Para o subdomínio `ads-mcp` funcionar com SSL, adicione:

| Tipo | Nome | Conteúdo | Proxy |
|---|---|---|---|
| A | `ads-mcp` | `72.60.163.179` | DNS only (cinza) |

Após adicionar, rodar no VPS:
```bash
certbot --nginx -d ads-mcp.redeastrum.com.br --non-interactive --agree-tos -m contato@lensshop.com.br
```

---

## Comandos úteis no VPS

```bash
# Status dos processos
pm2 list

# Ver logs em tempo real
pm2 logs google-ads-mcp

# Reiniciar manualmente
pm2 restart google-ads-mcp

# Deploy manual (mesmo que o webhook)
/root/google-ads-mcp/deploy.sh

# Testar o servidor MCP localmente
curl http://localhost:8090/mcp
```

---

## Conectar no claude.ai

1. Acessar [claude.ai/customize/connectors](https://claude.ai/customize/connectors)
2. Adicionar conector MCP com URL: `https://ads-mcp.redeastrum.com.br/mcp`
3. Tipo de autenticação: nenhuma (protegido por nginx)

---

## Branch

- **`main`** — upstream original (google/google-ads-mcp)
- **`lensshop/mutate-tools`** — nossa versão com ferramentas de escrita e deploy

Para sincronizar com upstream: `sync-upstream.bat`
