from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class BaseMaxApiModel(BaseModel):
    cmd: int
    opcode: int
    payload: Any
    seq: int
    ver: int


class MaxUserAgent(BaseModel):
    deviceType: str
    locale: str
    deviceLocale: str
    osVersion: str
    deviceName: str
    headerUserAgent: str
    appVersion: str
    screen: str
    timezone: str


class MaxAuthRequest(BaseModel):
    userAgent: MaxUserAgent
    deviceId: str


class MaxTokenData(BaseModel):
    interactive: bool
    token: str
    chatsCount: int
    chatsSync: int
    contactsSync: int
    presenceSync: int
    draftsSync: int


class MaxAuthTokenRequest(BaseMaxApiModel):
    cmd: int = 0
    opcode: int = 19
    ver: int = 11
    payload: MaxTokenData


class MaxGetMessagesRequestPayload(BaseModel):
    chatId: int
    from_: int = Field(alias="from", default_factory=lambda: int(datetime.now().timestamp()*1000))
    forward: int
    backward: int
    getMessages: bool


class MaxGetMessagesRequest(BaseMaxApiModel):
    ver: int = 11
    cmd: int = 0
    opcode: int = 49
    payload: MaxGetMessagesRequestPayload
