import asyncio
import json
import os
from uuid import uuid4
from httpx import AsyncClient
from websockets import Origin
from websockets.asyncio.client import connect
import logging
from dotenv import load_dotenv

from max import BaseMaxApiModel, MaxAuthTokenRequest, MaxUserAgent, MaxTokenData, MaxGetMessagesRequest, MaxGetMessagesRequestPayload


load_dotenv()


logging.basicConfig(
    format="%(asctime)s %(message)s",
    level=logging.DEBUG,
)


def get_last_msg_id():
    try:
        content = open("curr_msg.txt", "r+").readline().strip()
        return content if content else None
    except FileNotFoundError:
        return None

def set_last_msg_id(msg_id):
    with open("curr_msg.txt", "w") as f:
        f.write(str(msg_id))


async def max_connect():
    url = "wss://ws-api.oneme.ru/websocket"
    last_message_id = get_last_msg_id()
    seq = 0

    async with connect(
        url,
        user_agent_header="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        origin=Origin("https://web.max.ru"),
    ) as ws:
        initial_session_request = BaseMaxApiModel(
            cmd=0,
            ver=11,
            seq=seq,
            opcode=6,
            payload={
                "deviceId": str(uuid4()),
                "userAgent": MaxUserAgent(
                    deviceType=os.getenv("MAX_DEVICE_TYPE"),
                    locale=os.getenv("MAX_LOCALE"),
                    deviceLocale=os.getenv("MAX_DEVICE_LOCALE"),
                    osVersion=os.getenv("MAX_OS_VERSION"),
                    headerUserAgent=os.getenv("MAX_USER_AGENT"),
                    appVersion=os.getenv("MAX_APP_VERSION"),
                    screen=os.getenv("MAX_SCREEN"),
                    timezone=os.getenv("MAX_TZ"),
                    deviceName=os.getenv("MAX_DEVICE_NAME")
                ).model_dump(),
            },
        )
        await ws.send(
            json.dumps(initial_session_request.model_dump())
        )
        seq += 1

        try:
            res = BaseMaxApiModel(**json.loads(await ws.recv()))
            logging.info(f"Initial session established: opcode={res.opcode}")
        except Exception as e:
            logging.error(f"Error while fetching initial data in MAX WS: {e}")
            return

        auth_request = MaxAuthTokenRequest(seq=seq, payload=MaxTokenData(interactive=True, token=os.getenv("MAX_AUTH_TOKEN"), chatsCount=40, chatsSync=0, contactsSync=0, presenceSync=0, draftsSync=0))
        await ws.send(
            json.dumps(auth_request.model_dump())
        )
        seq += 1

        try:
            res = BaseMaxApiModel(**json.loads(await ws.recv()))
            logging.info(f"Authorization successful: opcode={res.opcode}")
        except Exception as e:
            logging.error(f"Error while authorizing in MAX WS: {e}")
            return

        logging.info("Starting message polling loop...")
        
        try:
            while True:
                get_messages_request = MaxGetMessagesRequest(
                    seq=seq,
                    payload=MaxGetMessagesRequestPayload(
                        chatId=int(os.getenv("MAX_CHAT_ID")),
                        forward=0,
                        backward=30,
                        getMessages=True,
                    )
                )
                await ws.send(json.dumps(get_messages_request.model_dump(by_alias=True)))
                seq += 1
                
                res = json.loads(await ws.recv())
                messages = res.get("payload", {}).get("messages", [])
                
                if messages:
                    last_message = messages[-1]
                    current_msg_id = str(last_message.get("id", ""))
                    
                    if current_msg_id != last_message_id:
                        logging.info(f"New message detected! ID: {current_msg_id}")
                        logging.info(f"Message content: {last_message}")
                        
                        set_last_msg_id(current_msg_id)
                        last_message_id = current_msg_id
                        
                        client = AsyncClient(base_url=f"https://api.telegram.org/bot{os.getenv('TG_TOKEN')}")
                        if last_message.get("text"):
                            await client.post("/sendMessage", json={
                                "chat_id": os.getenv("TG_CHAT_ID"),
                                "text": f"<blockquote>{last_message.get('text')}</blockquote>",
                                "parse_mode": "html"
                            })
                        for attach in last_message.get("attaches", []):
                            await client.post("/sendPhoto", json={
                            "chat_id": os.getenv("TG_CHAT_ID"),
                            "photo": attach["baseUrl"]
                        })
                    else:
                        logging.debug("No new messages")
                else:
                    logging.warning("No messages received from chat")
                
                await asyncio.sleep(3)
                
        except Exception as e:
            logging.error(f"Error in message polling loop: {e}")
            raise


if __name__ == "__main__":
    try:
        asyncio.run(max_connect())
    except KeyboardInterrupt:
        logging.info("Application stopped")
    except Exception as e:
        logging.error(f"Application error: {e}")
