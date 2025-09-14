from __future__ import annotations
import logging, asyncio, time
from datetime import timedelta
from typing import Any, Dict
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .api import VeoovibesApi
from .const import DEFAULT_SCAN_INTERVAL, FAV_REFRESH_SECONDS

_LOGGER = logging.getLogger(__name__)

class VeoovibesCoordinator(DataUpdateCoordinator[Dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, api: VeoovibesApi, scan_interval: int = DEFAULT_SCAN_INTERVAL) -> None:
        super().__init__(
            hass,
            logger=_LOGGER,
            name="veoovibes",
            update_interval=timedelta(seconds=scan_interval),
        )
        self.api = api
        self._favorites_cache: Dict[str, Any] | None = None
        self._favorites_last: float = 0.0

    async def _async_update_data(self) -> Dict[str, Any]:
        rooms_resp = await self.api.list_rooms()
        rooms = rooms_resp.get("result") or {}
        rids = [str(k) for k in rooms.keys()] if isinstance(rooms, dict) else []
        _LOGGER.debug("veoovibes: loaded rooms: %s", rids)

        async def _one(rid: str):
            try:
                d = await self.api.room_player_status(rid)
                return rid, (d.get("result") or d)
            except Exception as e:
                _LOGGER.debug("room_player_status failed for %s: %s", rid, e)
                return rid, {}

        results = await asyncio.gather(*[_one(r) for r in rids], return_exceptions=False)
        room_status = {rid: data for rid, data in results}

        feedback = {}
        try:
            fb = await self.api.get_room_feedback(rids)
            feedback = fb.get("result") or {}
        except Exception as e:
            _LOGGER.debug("get_room_feedback failed: %s", e)

        now = time.time()
        favorites = self._favorites_cache
        if favorites is None or (now - self._favorites_last) > FAV_REFRESH_SECONDS:
            try:
                fav_resp = await self.api.list_favorites()
                favorites = fav_resp.get("result") or {}
                self._favorites_cache = favorites
                self._favorites_last = now
            except Exception as e:
                _LOGGER.debug("list_favorites failed: %s", e)

        return {"rooms": rooms, "room_status": room_status, "feedback": feedback, "favorites": favorites or {}}
