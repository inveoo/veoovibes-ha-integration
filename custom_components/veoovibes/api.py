from __future__ import annotations
from typing import Any, Dict, Iterable
from yarl import URL
import aiohttp
import logging

_LOGGER = logging.getLogger(__name__)

class VeoovibesApi:
    def __init__(self, session: aiohttp.ClientSession, host: str, api_key: str) -> None:
        self._session = session
        self._host = host
        self._api_key = api_key

    @property
    def host(self) -> str:
        return self._host

    def _url(self, path: str) -> URL:
        return URL.build(scheme="http", host=self._host) / "api" / "v1" / path

    async def _get(self, path: str, **params: Any) -> Dict[str, Any]:
        params = {"api_key": self._api_key, **{k: v for k, v in params.items() if v is not None}}
        timeout = aiohttp.ClientTimeout(total=10)
        async with self._session.get(self._url(path), params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            if data.get("status") != "succeeded":
                raise RuntimeError(f"API failed {path}: {data}")
            return data

    # ---------- Reads ----------
    async def list_rooms(self) -> Dict[str, Any]:
        return await self._get("listrooms")

    async def room_player_status(self, room: str | int) -> Dict[str, Any]:
        return await self._get("room_player_status", room=room)

    async def get_room_feedback(self, room_ids: Iterable[int | str]) -> Dict[str, Any]:
        params = [("api_key", self._api_key)]
        for r in room_ids:
            params.append(("room[]", str(r)))
        timeout = aiohttp.ClientTimeout(total=10)
        async with self._session.get(self._url("get_room_feedback"), params=params, timeout=timeout) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)
            if data.get("status") != "succeeded":
                raise RuntimeError(f"API failed get_room_feedback: {data}")
            return data

    async def list_favorites(self) -> Dict[str, Any]:
        return await self._get("listFavorites")

    # ---------- Controls (ROOM endpoints) ----------
    async def room_play(self, room: str | int) -> None:
        await self._get("room_play", room=room)

    async def room_stop(self, room: str | int) -> None:
        await self._get("room_stop", room=room)

    async def room_next(self, room: str | int) -> None:
        await self._get("room_next", room=room)

    async def room_prev(self, room: str | int) -> None:
        await self._get("room_prev", room=room)

    async def room_vol_set(self, room: str | int, vol: int) -> None:
        await self._get("room_vol_set", room=room, vol=vol)

    async def room_vol_up(self, room: str | int) -> None:
        await self._get("room_vol_up", room=room)

    async def room_vol_down(self, room: str | int) -> None:
        await self._get("room_vol_down", room=room)

    async def play_favorite(self, room: str | int, fav_id: str) -> None:
        await self._get("playfavorite", room=room, favId=fav_id)
