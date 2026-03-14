from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.components.http import HomeAssistantView

from .const import DOMAIN, PROXY_CONFIG_SCHEMA, PROXY_LIST_SCHEMA, ProxyConfigEntry
from .script_proxy import ScriptProxyView

import voluptuous as vol

_LOGGER = logging.getLogger(__name__)

PLATFORMS = []

CONFIG_SCHEMA = vol.Schema({
    DOMAIN: PROXY_LIST_SCHEMA,
}, extra=vol.ALLOW_EXTRA)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Setup YAML"""
    if DOMAIN in config:
        proxies = config[DOMAIN]

        # Validation
        try:
            validated_proxies = PROXY_LIST_SCHEMA(proxies)
            _LOGGER.info(f"Validated {len(validated_proxies)} proxy scripts")
        except vol.Invalid as err:
            _LOGGER.error(f"YAML validation failed: {err}")
            return False

        hass.data[DOMAIN] = validated_proxies

        for proxy_config in validated_proxies:
            view = ScriptProxyView(hass, proxy_config['id'], proxy_config)
            hass.http.register_view(view)
            _LOGGER.info(f"✅ Registered HTTP proxy: /{proxy_config['id']}")

    else:
        _LOGGER.warning("No proxy_scripts found in configuration.yaml")

    return True