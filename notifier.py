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
import re
import unicodedata
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient, events

BASE_DIR = Path(__file__).parent
KEYWORDS_FILE = BASE_DIR / "keywords.txt"

load_dotenv(BASE_DIR / ".env")

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
TARGET_CHAT_ID = int(os.environ["TARGET_CHAT_ID"])  # grupo privado onde chegam os alertas

# Opcional: IDs (separados por vírgula) para monitorar só grupos específicos.
# Vazio = monitora todos os grupos/canais que você participa.
MONITORED = {
    int(x) for x in os.getenv("MONITORED_CHATS", "").split(",") if x.strip()
}

# Ignora mensagens antigas ao iniciar
IGNORE_PAST = os.getenv("IGNORE_PAST", "true").lower() == "true"


# ---------------------------------------------------------------- filtro

def normalize(text: str) -> str:
    """Minusculas, sem acentos e com espaços repetidos colapsados."""
    nfkd = unicodedata.normalize("NFKD", text)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", no_accents).lower()


def load_keywords() -> list[str]:
    if not KEYWORDS_FILE.exists():
        return []
    return [
        line.strip()
        for line in KEYWORDS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def save_keywords(keywords: list[str]) -> None:
    KEYWORDS_FILE.write_text(
        "\n".join(sorted(set(keywords), key=str.lower)) + "\n", encoding="utf-8"
    )


def _kw_pattern(keyword: str) -> "re.Pattern[str]":
    """Regex da palavra-chave: ignora acento/case, espaços e hífens entre
    as partes ('air fryer' casa com 'airfryer' e 'air-fryer') e exige
    limites de palavra ('ssd' não casa com 'ssdex')."""
    parts = [re.escape(p) for p in normalize(keyword).split()]
    return re.compile(r"(?<!\w)" + r"[\s-]*".join(parts) + r"(?!\w)")


def find_matches(text: str, keywords: list[str]) -> list[str]:
    """Retorna as palavras-chave encontradas no texto (ignora acentos/case)."""
    haystack = normalize(text)
    return [kw for kw in keywords if _kw_pattern(kw).search(haystack)]


def build_message_link(chat, msg_id: int) -> str:
    if getattr(chat, "username", None):
        return f"https://t.me/{chat.username}/{msg_id}"
    # supergrupo/canal privado: t.me/c/<id sem o -100>/<msg>
    cid = str(chat.id)
    if cid.startswith("-100"):
        cid = cid[4:]
    return f"https://t.me/c/{cid}/{msg_id}"


# ---------------------------------------------------------------- clientes

user_client = TelegramClient(str(BASE_DIR / "user_session"), API_ID, API_HASH)
bot_client = TelegramClient(str(BASE_DIR / "bot_session"), API_ID, API_HASH)


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
    chat = await event.get_chat()
    if MONITORED and chat.id not in MONITORED:
        return
    if not event.raw_text:
        return

    matches = find_matches(event.raw_text, load_keywords())
    if matches:
        await send_alert(event, matches)


@user_client.on(events.NewMessage(pattern=r"^/(add|remover|listar|grupos|status)(\s|$)"))
async def command_handler(event):
    # comandos funcionam SOMENTE no grupo de alertas (só seu, só você e o bot)
    if not event.out:
        return
    if (await event.get_chat()).id != TARGET_CHAT_ID:
        return

    cmd, _, arg = event.raw_text.partition(" ")
    cmd = cmd.lstrip("/").lower()
    arg = arg.strip().lower()

    if cmd == "add" and arg:
        kws = load_keywords()
        if normalize(arg) in [normalize(k) for k in kws]:
            await event.reply(f"'{arg}' já está na lista.")
        else:
            kws.append(arg)
            save_keywords(kws)
            await event.reply(f"✅ '{arg}' adicionada. Lista agora: {', '.join(load_keywords())}")
    elif cmd == "remover" and arg:
        kws = load_keywords()
        remaining = [k for k in kws if normalize(k) != normalize(arg)]
        if len(remaining) == len(kws):
            await event.reply(f"'{arg}' não estava na lista.")
        else:
            save_keywords(remaining)
            await event.reply(f"🗑 '{arg}' removida.")
    elif cmd == "listar":
        kws = load_keywords()
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
        kws = load_keywords()
        await event.reply(
            f"✅ Monitorando {len(kws)} palavra(s) em "
            f"{'todos os grupos' if not MONITORED else str(len(MONITORED)) + ' grupo(s) selecionado(s)'}."
        )


# ---------------------------------------------------------------- main

async def main():
    await ensure_user_authorized()  # 1ª vez: telefone+código (PC) ou QR (Replit)
    await bot_client.start(bot_token=BOT_TOKEN)

    me = await user_client.get_me()
    print(f"✅ Conectado como {me.first_name} (@{me.username})")
    print(f"🔑 Palavras-chave: {len(load_keywords())}")
    print("📡 Monitorando... (comandos SÓ no grupo de alertas) [v1.2]")

    await asyncio.gather(
        user_client.run_until_disconnected(),
        bot_client.run_until_disconnected(),
    )


if __name__ == "__main__":
    asyncio.run(main())
