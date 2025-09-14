from __future__ import annotations
import logging, hashlib
from typing import Any, Optional
from homeassistant.components.media_player import MediaPlayerEntity
from homeassistant.components.media_player.const import MediaPlayerEntityFeature, MediaPlayerState
from homeassistant.components.media_player.browse_media import (
    BrowseMedia,
    MediaClass,
    MediaType,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback, async_get_current_platform
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CTX_FAVORITE
from .coordinator import VeoovibesCoordinator

_LOGGER = logging.getLogger(__name__)

BASE_FEATURES = (
    MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_STEP
    | MediaPlayerEntityFeature.BROWSE_MEDIA
    | MediaPlayerEntityFeature.PLAY_MEDIA
)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coord: VeoovibesCoordinator = data["coordinator"]
    api = data["api"]

    rooms = coord.data.get("rooms", {}) or {}
    entities = []
    for rid, rinfo in rooms.items():
        entities.append(VeoovibesRoom(api, coord, rid, rinfo, host=data["api"].host))
    async_add_entities(entities)

    platform = async_get_current_platform()
    platform.async_register_entity_service(
        "play_favorite",
        {
            "fav_id": str,
        },
        "async_play_favorite",
    )

class VeoovibesRoom(CoordinatorEntity[VeoovibesCoordinator], MediaPlayerEntity):
    _attr_has_entity_name = False  # explicit friendly name
    _attr_device_class = "speaker"

    def __init__(self, api, coordinator: VeoovibesCoordinator, room_id: str, room_info: dict[str, Any], host: str):
        super().__init__(coordinator)
        self.api = api
        self._room_id = str(room_id)
        self._room_name = room_info.get("name") or room_info.get("api_room_name") or f"Room {room_id}"
        self._friendly = f"veoovibes – {self._room_name}"
        self._attr_unique_id = f"veoovibes_room_{self._room_id}"
        self._attr_name = self._friendly
        self._attr_supported_features = BASE_FEATURES
        self._host = host

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, f"{self._host}-{self._room_id}")},
            manufacturer="inveoo GmbH",
            model="veoovibes",
            name=f"veoovibes – {self._room_name}",
            configuration_url=f"http://{self._host}",
        )

    # ---------- Helpers ----------
    def _rooms(self) -> dict[str, Any]:
        return self.coordinator.data.get("rooms", {}) or {}

    def _rp(self) -> dict[str, Any]:
        return (self.coordinator.data.get("room_status", {}) or {}).get(self._room_id, {})

    def _fb_text(self) -> dict[str, Any]:
        fb = self.coordinator.data.get("feedback", {}) or {}
        ptext = {}
        for e in fb.get("playertext", []) or []:
            ptext[str(e.get("roomid"))] = e
        return ptext.get(self._room_id, {})

    def _fb_vol(self) -> Optional[int]:
        fb = self.coordinator.data.get("feedback", {}) or {}
        for e in fb.get("roomvolume", []) or []:
            if str(e.get("roomid")) == self._room_id:
                try:
                    return int(e.get("roomvol"))
                except Exception:
                    return None
        return None

    def _fb_is_playing(self) -> bool:
        t = self._fb_text()
        for k in ("roomtext", "roomtitle", "roomartist", "roomalbum"):
            v = t.get(k)
            if isinstance(v, str) and v.strip():
                return True
        return False

    # ---------- Core state ----------
    @property
    def available(self) -> bool:
        r = self._rooms().get(self._room_id) or {}
        return bool(r.get("is_available", True))

    @property
    def state(self) -> Optional[str]:
        p = self._rp()
        status_code = (p.get("status_code") or "").lower()
        is_playing_flag = str(p.get("is_playing", "0")).lower() in ("1", "true", "yes")

        if status_code == "playing" or is_playing_flag:
            return MediaPlayerState.PLAYING
        if status_code in ("paused", "pause"):
            return MediaPlayerState.IDLE
        if self._fb_is_playing():
            return MediaPlayerState.PLAYING
        if status_code in ("stopped", "stop"):
            return MediaPlayerState.IDLE
        return MediaPlayerState.IDLE

    def _clean(self, s: Optional[str]) -> Optional[str]:
        if isinstance(s, str) and s.strip():
            return s.strip()
        return None

    @property
    def media_title(self) -> Optional[str]:
        p = self._rp()
        fb = self._fb_text()
        return self._clean(fb.get("roomtext")) or self._clean(p.get("title")) or self._clean(fb.get("roomtitle"))

    @property
    def media_artist(self) -> Optional[str]:
        p = self._rp()
        fb = self._fb_text()
        return self._clean(p.get("artist")) or self._clean(fb.get("roomartist"))

    @property
    def media_album_name(self) -> Optional[str]:
        p = self._rp()
        fb = self._fb_text()
        return self._clean(p.get("album")) or self._clean(fb.get("roomalbum"))

    @property
    def media_content_type(self) -> Optional[str]:
        return "music"

    def _cover(self) -> Optional[str]:
        p = self._rp()
        c = p.get("cover")
        return self._clean(c)

    def _meta_hash(self) -> str:
        t = self.media_title or ""
        a = self.media_artist or ""
        b = self.media_album_name or ""
        base = f"{t}|{a}|{b}".encode("utf-8", "ignore")
        return hashlib.sha1(base).hexdigest()[:8]

    @property
    def entity_picture(self) -> Optional[str]:
        url = self._cover()
        if not url:
            return None
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}cache={self._meta_hash()}"

    @property
    def volume_level(self) -> Optional[float]:
        p = self._rp()
        vol = p.get("current_volume")
        if vol is None:
            vol = self._fb_vol()
        try:
            return max(0.0, min(1.0, float(vol) / 100.0)) if vol is not None else None
        except Exception:
            return None

    # ---------- Controls ----------
    async def async_media_play(self) -> None:
        await self.api.room_play(self._room_id)
        await self.coordinator.async_request_refresh()

    async def async_media_stop(self) -> None:
        await self.api.room_stop(self._room_id)
        await self.coordinator.async_request_refresh()

    async def async_media_next_track(self) -> None:
        await self.api.room_next(self._room_id)
        await self.coordinator.async_request_refresh()

    async def async_media_previous_track(self) -> None:
        await self.api.room_prev(self._room_id)
        await self.coordinator.async_request_refresh()

    async def async_volume_up(self) -> None:
        await self.api.room_vol_up(self._room_id)
        await self.coordinator.async_request_refresh()

    async def async_volume_down(self) -> None:
        await self.api.room_vol_down(self._room_id)
        await self.coordinator.async_request_refresh()

    async def async_set_volume_level(self, volume: float) -> None:
        vol = max(0, min(100, int(round(volume * 100))))
        await self.api.room_vol_set(self._room_id, vol)
        await self.coordinator.async_request_refresh()

    # ---------- Favorites ----------
    async def async_play_favorite(self, fav_id: str) -> None:
        await self.api.play_favorite(self._room_id, fav_id)
        await self.coordinator.async_request_refresh()

    async def async_browse_media(self, media_content_type=None, media_content_id=None) -> BrowseMedia:
        # Root for this room
        if media_content_type is None:
            root = BrowseMedia(
                title=self._friendly,
                media_class=MediaClass.DIRECTORY,
                media_content_id="library",
                media_content_type="library",
                can_play=False,
                can_expand=True,
                children=[],
            )
            root.children.append(
                BrowseMedia(
                    title="Favoriten",
                    media_class=MediaClass.DIRECTORY,
                    media_content_id=f"favorites",
                    media_content_type=CTX_FAVORITE,
                    can_play=False,
                    can_expand=True,
                )
            )
            return root

        # Favorites list
        if media_content_type == CTX_FAVORITE:
            favs = (self.coordinator.data.get("favorites") or {}) if self.coordinator.data else {}
            children = []
            # result is dict keyed by favId-like keys
            for k, v in favs.items():
                fav_id = v.get("favId") or k
                title = v.get("name") or fav_id
                image = v.get("image")
                mclass = MediaClass.MUSIC if (v.get("type") or "").lower() in ("playlist", "spotify", "applemusic") else MediaClass.CHANNEL
                child = BrowseMedia(
                    title=title,
                    media_class=mclass,
                    media_content_id=fav_id,
                    media_content_type=CTX_FAVORITE,
                    can_play=True,
                    can_expand=False,
                    thumbnail=image,
                )
                children.append(child)
            # Sort by title
            children.sort(key=lambda x: (x.title or "").lower())
            return BrowseMedia(
                title="Favoriten",
                media_class=MediaClass.DIRECTORY,
                media_content_id="favorites",
                media_content_type=CTX_FAVORITE,
                can_play=False,
                can_expand=True,
                children=children,
            )

        # Fallback
        return BrowseMedia(
            title=self._friendly,
            media_class=MediaClass.DIRECTORY,
            media_content_id="library",
            media_content_type="library",
            can_play=False,
            can_expand=True,
        )

    async def async_play_media(self, media_type, media_id, **kwargs) -> None:
        if media_type == CTX_FAVORITE:
            await self.async_play_favorite(media_id)
            return
        # otherwise ignore
