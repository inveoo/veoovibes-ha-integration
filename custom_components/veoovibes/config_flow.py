from __future__ import annotations
from typing import Any
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from .const import DOMAIN, CONF_HOST, CONF_API_KEY, CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
from .api import VeoovibesApi

class VeoovibesConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = VeoovibesApi(session, user_input[CONF_HOST], user_input[CONF_API_KEY])
            try:
                data = await api.list_rooms()
                if data.get("status") != "succeeded":
                    errors["base"] = "cannot_connect"
                else:
                    await self.async_set_unique_id(f"veoovibes:{user_input[CONF_HOST]}")
                    self._abort_if_unique_id_configured()
                    return self.async_create_entry(title=f"veoovibes ({user_input[CONF_HOST]})", data=user_input)
            except Exception:
                errors["base"] = "cannot_connect"

        schema = vol.Schema({
            vol.Required(CONF_HOST): str,
            vol.Required(CONF_API_KEY): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_import(self, import_config: dict[str, Any]) -> FlowResult:
        return await self.async_step_user(import_config)

class VeoovibesOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="Options", data=user_input)

        schema = vol.Schema({
            vol.Optional(CONF_SCAN_INTERVAL, default=self.config_entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)): vol.All(int, vol.Range(min=1, max=30)),
        })
        return self.async_show_form(step_id="init", data_schema=schema)

async def async_get_options_flow(config_entry: config_entries.ConfigEntry):
    return VeoovibesOptionsFlowHandler(config_entry)
