import asyncio
import json
import logging
import os
from typing import AsyncIterator
from uuid import uuid4

from websockets import Origin
from websockets.asyncio.client import connect

from max import BaseMaxApiModel, MaxAuthTokenRequest, MaxTokenData, MaxUserAgent


URL = "wss://ws-api.oneme.ru/websocket"
ORIGIN = "https://web.max.ru"
KEEPALIVE_INTERVAL = 2.5

OPCODE_KEEPALIVE = 1
OPCODE_INIT_SESSION = 6
OPCODE_AUTH = 19
OPCODE_PUSH_MESSAGE = 128


class MaxClient:
    def __init__(self) -> None:
        self._connect_cm = None
        self._ws = None
        self._seq = 0
        self._keepalive_task: asyncio.Task | None = None

    async def __aenter__(self) -> "MaxClient":
        self._connect_cm = connect(
            URL,
            user_agent_header=os.getenv("MAX_USER_AGENT"),
            origin=Origin(ORIGIN),
        )
        self._ws = await self._connect_cm.__aenter__()
        await self._init_session()
        await self._authenticate()
        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
        return self

    async def __aexit__(self, exc_type, exc, tb):
        if self._keepalive_task is not None:
            if not self._keepalive_task.done():
                self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except BaseException:
                pass
        return await self._connect_cm.__aexit__(exc_type, exc, tb)

    async def _send(self, payload: dict) -> None:
        await self._ws.send(json.dumps({**payload, "seq": self._seq}))
        self._seq += 1

    async def _recv(self) -> dict:
        return json.loads(await self._ws.recv())

    async def _init_session(self) -> None:
        request = BaseMaxApiModel(
            cmd=0,
            ver=11,
            seq=0,
            opcode=OPCODE_INIT_SESSION,
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
                    deviceName=os.getenv("MAX_DEVICE_NAME"),
                ).model_dump(),
            },
        )
        await self._send(request.model_dump())
        res = BaseMaxApiModel(**await self._recv())
        logging.info(f"Initial session established: opcode={res.opcode}")

    async def _authenticate(self) -> None:
        request = MaxAuthTokenRequest(
            seq=0,
            payload=MaxTokenData(
                interactive=True,
                token=os.getenv("MAX_AUTH_TOKEN"),
                chatsCount=40,
                chatsSync=0,
                contactsSync=0,
                presenceSync=0,
                draftsSync=0,
            ),
        )
        await self._send(request.model_dump())
        res = BaseMaxApiModel(**await self._recv())
        logging.info(f"Authorization successful: opcode={res.opcode}")

    async def _keepalive_loop(self) -> None:
        while True:
            await asyncio.sleep(KEEPALIVE_INTERVAL)
            await self._send({
                "ver": 11,
                "cmd": 0,
                "opcode": OPCODE_KEEPALIVE,
                "payload": {"interactive": True},
            })

    async def events(self) -> AsyncIterator[dict]:
        async for raw in self._ws:
            yield json.loads(raw)

    async def messages(self, chat_id: int | None = None) -> AsyncIterator[dict]:
        async for event in self.events():
            opcode = event.get("opcode")
            if opcode != OPCODE_PUSH_MESSAGE:
                logging.debug(f"Ignoring opcode={opcode}")
                continue
            payload = event.get("payload", {})
            if chat_id is not None and payload.get("chatId") != chat_id:
                logging.debug(f"Skip message from chatId={payload.get('chatId')}")
                continue
            message = payload.get("message")
            if not message:
                continue
            if message.get("link", {}).get("type") == "FORWARD":
                message = message["link"]["message"]
            yield message
