# Configuração de e-mail

O EvoCRM usa duas configurações diferentes para e-mail:

- **E-mail de entrada**: recebe mensagens e cria ou atualiza conversas.
- **Canal de e-mail**: define a caixa postal usada pelo CRM para ler mensagens
  via IMAP e responder via SMTP.

## 1. Variáveis SMTP do deploy

No arquivo `.env` do host, configure o SMTP padrão usado pelo Rails para
notificações e tarefas de e-mail:

```dotenv
SMTP_ADDRESS=mail.example.com
SMTP_PORT=587
SMTP_DOMAIN=example.com
SMTP_AUTHENTICATION=login
SMTP_ENABLE_STARTTLS_AUTO=true
SMTP_SSL=false
SMTP_USERNAME=contato@example.com
SMTP_PASSWORD=senha-ou-token
```

Para a porta `587`, use STARTTLS e mantenha `SMTP_SSL=false`. Não combine
`SMTP_SSL=true` com a porta 587: isso tenta SSL implícito e causa o erro
`wrong version number`.

Depois de alterar o `.env`, recrie os serviços que enviam e-mail:

```bash
cd /root/projects/evo-crm-community
docker compose up -d --force-recreate evo-crm evo-crm-sidekiq
```

Para SSL implícito, use somente a porta indicada pelo provedor, normalmente
465, com `SMTP_SSL=true` e `SMTP_ENABLE_STARTTLS_AUTO=false`.

## 2. Configurar o e-mail de entrada

No painel administrativo, abra **E-mail de Entrada** e selecione o provedor.
Para Mailgun, informe:

- chave de assinatura do Mailgun;
- domínio de entrada, por exemplo `mg.example.com`.

No Mailgun, crie uma rota para encaminhar as mensagens ao endereço técnico
exibido pelo EvoCRM. O domínio usado na rota deve ser o mesmo configurado no
EvoCRM.

Configure no DNS do domínio de entrada:

- registros MX apontando para os MX do Mailgun;
- SPF e DKIM conforme o domínio configurado no Mailgun.

Não use o MX do domínio principal para o Mailgun se ele já aponta para outro
servidor de e-mail. Prefira um subdomínio dedicado, como `mg.example.com`.

## 3. Configurar um canal de e-mail

Crie ou edite o canal em **Configurações do Admin → Canais → E-mail**. Para
uma caixa postal comum, informe:

### IMAP (recebimento)

```text
Servidor: mail.example.com
Porta: 993
SSL/TLS: habilitado
Usuário: contato@example.com
Senha: senha ou token da caixa postal
```

Ative o IMAP no canal. O worker busca novas mensagens periodicamente; a
execução também pode ser disparada manualmente pela ação de sincronização,
quando disponível na instalação.

### SMTP (respostas)

```text
Servidor: mail.example.com
Porta: 587
STARTTLS: habilitado
SSL implícito: desabilitado
Autenticação: login
Usuário: contato@example.com
Senha: senha ou token da caixa postal
```

Salve o canal e envie uma nova mensagem de teste. Mensagens que falharam
antes da correção continuam marcadas como falhas; é necessário reenviá-las ou
criar uma nova resposta.

## 4. Diagnóstico

Confira as variáveis carregadas pelo worker sem exibir senhas:

```bash
docker exec evo-crm-community-evo-crm-sidekiq-1 \
  sh -lc 'env | grep -E "^(SMTP_SSL|SMTP_TLS|SMTP_ENABLE_STARTTLS_AUTO|SMTP_PORT|SMTP_ADDRESS)="'
```

O resultado esperado para STARTTLS é:

```text
SMTP_PORT=587
SMTP_ENABLE_STARTTLS_AUTO=true
SMTP_SSL=false
```

Consulte os logs de envio:

```bash
docker logs --tail 200 evo-crm-community-evo-crm-sidekiq-1 \
  | grep -Ei 'EmailReplyWorker|Failed delivery|SMTP|SSL|STARTTLS'
```

O erro `SSL_connect ... wrong version number` indica que SSL implícito está
sendo usado em uma porta STARTTLS. Corrija as três opções acima e recrie o
worker.
