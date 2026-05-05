import asyncio
import logging
import os
import time

from dotenv import load_dotenv
from httpx import AsyncClient
from websockets.exceptions import ConnectionClosed

from max_client import MaxClient


load_dotenv()


logging.basicConfig(
    format="%(asctime)s %(message)s",
    level=logging.DEBUG,
)


async def forward_to_telegram(message: dict, tg: AsyncClient) -> None:
    chat_id = os.getenv("TG_CHAT_ID")
    text = message.get("text")
    if text:
        await tg.post("/sendMessage", json={
            "chat_id": chat_id,
            "text": f"<blockquote>{text}</blockquote>",
            "parse_mode": "html",
        })
    for attach in message.get("attaches", []):
        await tg.post("/sendPhoto", json={
            "chat_id": chat_id,
            "photo": attach["baseUrl"],
        })


async def run_forever() -> None:
    target_chat_id = int(os.getenv("MAX_CHAT_ID"))
    backoff = 1
    async with AsyncClient(base_url=f"https://api.telegram.org/bot{os.getenv('TG_TOKEN')}") as tg:
        while True:
            started = time.monotonic()
            try:
                async with MaxClient() as client:
                    logging.info("Listening for push events...")
                    async for message in client.messages(chat_id=target_chat_id):
                        logging.info(f"New message: id={message.get('id')} sender={message.get('sender')}")
                        await forward_to_telegram(message, tg)
            except (ConnectionClosed, OSError) as e:
                logging.warning(f"WS disconnected: {e}")
            except Exception:
                logging.exception("Unexpected failure in MAX session")
            if time.monotonic() - started > 60:
                backoff = 1
            logging.info(f"Reconnecting in {backoff}s...")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30)


if __name__ == "__main__":
    try:
        asyncio.run(run_forever())
    except KeyboardInterrupt:
        logging.info("Application stopped")
