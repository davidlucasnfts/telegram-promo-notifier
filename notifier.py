"""
Notificador de promoções do Telegram.

Usa a SUA conta (Telethon) para ouvir os grupos de promoções que você
já participa, filtra pelas palavras-chave de keywords.txt e envia os
alertas por um BOT SEU para um grupo privado seu.

Comandos (envie para "Mensagens Salvas" da sua própria conta):
    /add <palavra>      adiciona uma palavra-chave
    /remover <palavra>  remove uma palavra-chave
    /listar             lista as palavras-chave ativas
    /grupos             lista os grupos/canais monitorados
    /status             mostra se está tudo rodando
"""

import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events

from keywords import find_matches, load_keywords, normalize, save_keywords

BASE_DIR = Path(__file__).parent
KEYWORDS_FILE = BASE_DIR / "keywords.txt"

load_dotenv(BASE_DIR / ".env")


def _require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            f"❌ Variável de ambiente {name} não configurada. "
            "Copie .env.example para .env e preencha."
        )
    return value


API_ID = int(_require_env("API_ID"))
API_HASH = _require_env("API_HASH")
BOT_TOKEN = _require_env("BOT_TOKEN")
TARGET_CHAT_ID = int(_require_env("TARGET_CHAT_ID"))  # grupo privado onde chegam os alertas

# Opcional: IDs (separados por vírgula) para monitorar só grupos específicos.
# Vazio = monitora todos os grupos/canais que você participa.
MONITORED = {
    int(x) for x in os.getenv("MONITORED_CHATS", "").split(",") if x.strip()
}

# Ignora mensagens antigas ao iniciar
IGNORE_PAST = os.getenv("IGNORE_PAST", "true").lower() == "true"


# ---------------------------------------------------------------- clientes

user_client = TelegramClient(str(BASE_DIR / "user_session"), API_ID, API_HASH)
bot_client = TelegramClient(str(BASE_DIR / "bot_session"), API_ID, API_HASH)

PAUSED = False  # /parar e /continuar controlam os alertas


def render_qr(url: str) -> None:
    try:
        import qrcode
    except ImportError:
        print("QR URL:", url)
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.print_ascii(invert=True)


async def ensure_user_authorized() -> None:
    if await user_client.is_user_authorized():
        return
    # 1) tenta login interativo (quando roda num PC/terminal com teclado)
    try:
        await user_client.start()  # pede telefone + código via input()
        return
    except EOFError:
        pass  # sem entrada interativa (ex.: console de workflow do Replit)
    # 2) login por QR: aparece no console e é escaneado pelo app do celular
    from telethon.errors import SessionPasswordNeededError
    print("📱 Escaneie o QR abaixo com o Telegram do celular:")
    print("   Configurações → Dispositivos → Conectar dispositivo")
    qr = await user_client.qr_login()
    while not await user_client.is_user_authorized():
        render_qr(qr.url)
        try:
            await qr.wait(timeout=30)
        except asyncio.TimeoutError:
            await qr.recreate()  # QR expirou, gera outro
        except SessionPasswordNeededError:
            raise SystemExit(
                "Sua conta tem verificação em 2 etapas (senha). "
                "Rode uma vez num PC local para digitar a senha, ou desative-a temporariamente."
            )


def build_message_link(chat, msg_id: int) -> str:
    if getattr(chat, "username", None):
        return f"https://t.me/{chat.username}/{msg_id}"
    # supergrupo/canal privado: t.me/c/<id sem o -100>/<msg>
    cid = str(chat.id)
    if cid.startswith("-100"):
        cid = cid[4:]
    return f"https://t.me/c/{cid}/{msg_id}"


async def send_alert(event, matches: list[str]) -> None:
    chat = await event.get_chat()
    title = getattr(chat, "title", None) or getattr(chat, "first_name", "grupo")
    sender = await event.get_sender()
    author = getattr(sender, "first_name", None) or "desconhecido"
    link = build_message_link(chat, event.message.id)
    text = event.raw_text or "(mensagem sem texto — possivelmente foto/mídia)"

    if len(text) > 800:
        text = text[:800] + "…"

    await bot_client.send_message(
        TARGET_CHAT_ID,
        f"🔔 <b>Promoção detectada</b>\n"
        f"📌 Grupo: <b>{title}</b>\n"
        f"🔑 Palavras: <code>{', '.join(matches)}</code>\n"
        f"👤 {author}\n\n"
        f"{text}\n\n"
        f"🔗 {link}",
        parse_mode="html",
        link_preview=False,
    )


@user_client.on(events.NewMessage)
async def monitor_handler(event):
    # só grupos/canais
    if not (event.is_group or event.is_channel):
        return
    if PAUSED:
        return
    chat = await event.get_chat()
    if MONITORED and chat.id not in MONITORED:
        return
    if not event.raw_text:
        return

    matches = find_matches(event.raw_text, load_keywords(KEYWORDS_FILE))
    if matches:
        await send_alert(event, matches)


@user_client.on(events.NewMessage(pattern=r"^/(add|remover|listar|grupos|status|parar|continuar)(\s|$)"))
async def command_handler(event):
    # comandos funcionam SOMENTE no grupo de alertas (só seu, só você e o bot)
    if not event.out:
        return
    chat = await event.get_chat()
    if chat.id != TARGET_CHAT_ID:
        # diagnostico: avisa no proprio grupo qual é o ID dele (ajuda a corrigir o .env)
        title = getattr(chat, "title", "sem título")
        try:
            await bot_client.send_message(
                chat.id,
                f"⚠️ Este chat não é o grupo de alertas configurado.\n"
                f"📌 ID deste chat: <code>{chat.id}</code> ({title})\n"
                f"Corrija o TARGET_CHAT_ID no arquivo .env com o ID deste chat e reinicie.",
                parse_mode="html",
            )
        except Exception as e:
            print(f"⚠️ comando ignorado no chat {chat.id}: {e}")
        return

    global PAUSED
    cmd, _, arg = event.raw_text.partition(" ")
    cmd = cmd.lstrip("/").lower()
    arg = arg.strip().lower()

    if cmd == "parar":
        PAUSED = True
        await event.reply("⏸ Monitoramento PAUSADO. Nenhum alerta será enviado. Mande /continuar para retomar.")
        return
    if cmd == "continuar":
        PAUSED = False
        await event.reply("▶️ Monitoramento RETOMADO. Alertas ativos novamente.")
        return

    if cmd == "add" and arg:
        kws = load_keywords(KEYWORDS_FILE)
        if normalize(arg) in [normalize(k) for k in kws]:
            await event.reply(f"'{arg}' já está na lista.")
        else:
            kws.append(arg)
            save_keywords(kws, KEYWORDS_FILE)
            await event.reply(f"✅ '{arg}' adicionada. Lista agora: {', '.join(load_keywords(KEYWORDS_FILE))}")
    elif cmd == "remover" and arg:
        kws = load_keywords(KEYWORDS_FILE)
        remaining = [k for k in kws if normalize(k) != normalize(arg)]
        if len(remaining) == len(kws):
            await event.reply(f"'{arg}' não estava na lista.")
        else:
            save_keywords(remaining, KEYWORDS_FILE)
            await event.reply(f"🗑 '{arg}' removida.")
    elif cmd == "listar":
        kws = load_keywords(KEYWORDS_FILE)
        await event.reply(
            f"📋 {len(kws)} palavra(s) monitorada(s):\n" + ("\n".join(f"• {k}" for k in kws) if kws else "(lista vazia)")
        )
    elif cmd == "grupos":
        lines = []
        async for d in user_client.iter_dialogs():
            if d.is_group or d.is_channel:
                mark = "👁" if (not MONITORED or d.id in MONITORED) else "⏸"
                lines.append(f"{mark} {d.name} (<code>{d.id}</code>)")
        await event.reply("Grupos/canais que você participa:\n" + "\n".join(lines[:60]))
    elif cmd == "status":
        kws = load_keywords(KEYWORDS_FILE)
        await event.reply(
            f"✅ Monitorando {len(kws)} palavra(s) em "
            f"{'todos os grupos' if not MONITORED else str(len(MONITORED)) + ' grupo(s) selecionado(s)'}.")


# ---------------------------------------------------------------- main

async def main():
    await ensure_user_authorized()  # 1ª vez: telefone+código (PC) ou QR (Replit)
    await bot_client.start(bot_token=BOT_TOKEN)

    me = await user_client.get_me()
    print(f"✅ Conectado como {me.first_name} (@{me.username})")
    print(f"🔑 Palavras-chave: {len(load_keywords(KEYWORDS_FILE))}")
    print("📡 Monitorando... (comandos SÓ no grupo de alertas) [v1.2]")

    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected(),
    )


if __name__ == "__main__":
    asyncio.run(main())
