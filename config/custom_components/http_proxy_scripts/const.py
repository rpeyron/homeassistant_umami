from typing import TypedDict
import voluptuous as vol
from homeassistant.config_entries import ConfigEntry

DOMAIN = "proxy_scripts"


class ProxyConfig(TypedDict):
    id: str
    script: str
    args: list[str]

ProxyConfigEntry = ConfigEntry[ProxyConfig]

PROXY_CONFIG_SCHEMA = vol.Schema({
    vol.Required('id'): str,
    vol.Required('script'): str,
    vol.Optional('args', default=[]): [str],
})

PROXY_LIST_SCHEMA = vol.Schema([PROXY_CONFIG_SCHEMA])

