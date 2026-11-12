# 🔔 Notificador de Promoções do Telegram

Projeto pessoal, separado do ReVende. Monitora os grupos de promoções que você
já participa **com a sua própria conta** (via Telethon), filtra pelas palavras-chave
que você definir e te avisa por um **bot seu** em um **grupo privado seu**.

```
grupo de promoções ──► sua conta (script) ──filtra──► seu bot ──► seu grupo privado
```

## 1. Requisitos

- Python 3.9+
- Conta no Telegram (a sua, normal)

## 2. Testes

O projeto inclui testes unitários para a lógica pura de filtro de palavras-chave
(`normalize`, `load_keywords`, `save_keywords`, `find_matches`). Eles não
precisam de conta do Telegram nem de variáveis de ambiente.

```bash
python -m unittest test_keywords.py -v
```

## 3. Setup (primeira vez, ~10 min)

### 3.1 API ID e Hash (para o script acessar sua conta)

1. Acesse <https://my.telegram.org> e faça login com seu número do Telegram.
2. Vá em **API Development Tools → Create Application** (nome e plataforma: Desktop).
3. Anote o **api_id** e **api_hash**.

### 3.2 Criar o bot

1. No Telegram, converse com **@BotFather**.
2. Envie `/newbot`, escolha um nome e um username (deve terminar em `bot`).
3. Anote o **token** recebido.

### 3.3 Criar o grupo privado dos alertas

1. Crie um grupo no Telegram (pode ser só você + o bot).
2. Adicione o seu bot ao grupo e **promova a administrador** (para poder postar).
3. Mande qualquer mensagem no grupo (facilita descobrir o ID).
4. Para descobrir o **ID do grupo**: encaminhe qualquer mensagem do grupo para
   **@userinfobot** — ele mostra o ID (formato `-100...`).

### 3.4 Configurar o projeto

```bash
cd telegram-promo-notifier
pip install -r requirements.txt
cp .env.example .env   # no Windows: copy .env.example .env
```

Edite o `.env` com os 4 valores: `API_ID`, `API_HASH`, `BOT_TOKEN`, `TARGET_CHAT_ID`.
Edite o `keywords.txt` com as palavras-chave que você procura (ex: `ssd`, `air fryer`).

### 3.5 Rodar

```bash
python notifier.py
```

Na primeira vez ele pede seu telefone (com DDI, ex: `+55119...`) e o código
de login do Telegram. Depois disso a sessão fica salva (`user_session.session`)
e não pede mais.

## 4. Comandos

Envie para as suas **Mensagens Salvas** (Favoritos) da sua própria conta:

| Comando | O que faz |
|---|---|
| `/add ryzen 7` | adiciona palavra-chave |
| `/remover ryzen 7` | remove palavra-chave |
| `/listar` | mostra as palavras ativas |
| `/grupos` | lista grupos/canais que você participa (com IDs) |
| `/status` | resumo do que está sendo monitorado |

O filtro ignora maiúsculas/minúsculas e acentos: procurar `air fryer` também
pega `AirFryer` e `AIR FRYER`.

## 5. Rodando na nuvem (grátis) — com ressalvas

Serviços gratuitos **dormem/resetam**, então o monitoramento pode parar sem aviso.
Opções, do mais estável para o menos:

- **Seu PC ligado** — o mais confiável "de graça".
- **Oracle Cloud Free Tier** (VPS grátis de verdade, sempre ligado) — o melhor
  custo-benefício se quiser nuvem de verdade sem pagar.
- **Replit (free)** — sobe fácil, mas hiberna; existe "keep-alive" por ping, mas
  viola os termos e é instável.
- **Google Colab** — desconecta após ~12h/idle; serve para testar, não para produção.

Em qualquer nuvem Linux:

```bash
git clone <seu-repo> && cd telegram-promo-notifier
pip install -r requirements.txt
# crie o .env na mão (nano .env) — NUNCA commite o .env
nohup python notifier.py > log.txt 2>&1 &
```

Para manter rodando de verdade, use `systemd` ou `pm2` (exemplos podem ser
adicionados depois, se quiser).

## 6. Segurança

- **Nunca compartilhe** `API_HASH`, `BOT_TOKEN` nem os arquivos `*.session`
  (a session equivale a senha da sua conta). O `.env` e as sessions já estão
  no `.gitignore`.
- O script usa seu `api_id` apenas para ler mensagens de grupos que você
  **já participa** — nada de entrar em grupos por você.
- Os comandos do bot só funcionam no grupo de alertas configurado
  (`TARGET_CHAT_ID`). Se alguém tentar usá-los em outro chat, o bot responde
  apenas com o ID daquele chat — sem expor o `TARGET_CHAT_ID` real.
- O `.env` é validado na inicialização: se faltar alguma variável obrigatória,
  o script encerra com uma mensagem clara antes de tentar conectar.

## 7. Estrutura

```
telegram-promo-notifier/
├── notifier.py        # script principal (orquestração Telegram)
├── keywords.py        # lógica pura de filtro de palavras-chave
├── test_keywords.py   # testes unitários do filtro
├── keywords.txt       # suas palavras-chave
├── requirements.txt
├── .env.example       # modelo de configuração
└── README.md
```

Arquivos gerados na 1ª execução: `.env`, `user_session.session`,
`bot_session.session` — todos pessoais, não versionar.
