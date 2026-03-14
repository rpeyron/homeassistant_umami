import logging
from typing import Any
import shlex
import subprocess
import json

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN, ProxyConfig

_LOGGER = logging.getLogger(__name__)

# https://github.com/home-assistant/core/blob/dev/homeassistant/helpers/http.py#L107

class ScriptProxyView(HomeAssistantView):
    url = "/api/proxy_scripts"
    name = "api:proxy_scripts"
    extra_urls: list[str] = []
    requires_auth = True
    cors_allowed = False

    def __init__(self, hass: HomeAssistant, entry_id: str, entry_data: ProxyConfig) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.entry_data = entry_data

        id = self.entry_data['id']

        self.url = f"/api/{DOMAIN}/{id}"
        self.name = f"api:{DOMAIN}_{id}"
        _LOGGER.info(f"Registered ScriptProxyView at {self.url} with entry data: {entry_data}")

    async def get(self, request) -> Any:
        query_params = dict(request.query)
        script = self.entry_data['script']
        _LOGGER.info(f"ScriptProxy get {query_params} -> running script: {script}")

        try:
            result = subprocess.run(shlex.split(script) + self.entry_data.get('args', []),
                                    capture_output=True, text=True)

            if result.returncode != 0:
                return self.json({
                    "error": "Script execution failed",
                    "stderr": result.stderr,
                    "stdout": result.stdout
                    }, status_code=400)

            data = json.loads(result.stdout)

            return self.json(data, status_code = (400 if (data and "error" in data and data["error"]) else 200))

        except subprocess.SubprocessError as e:
            _LOGGER.error(f"Error occurred while running script: {e}")
            return self.json({
                "error": "Script execution failed",
                "stderr": str(e)
            }, status_code=400)

        except subprocess.TimeoutExpired:
            _LOGGER.error("Script execution timed out")
            return self.json({
                "error": "Script execution timed out"
            }, status_code=500)

        except subprocess.CalledProcessError as e:
            _LOGGER.error(f"Script execution failed: {e.stderr}")
            return self.json({
                "error": "Script execution failed",
                "stderr": e.stderr
            }, status_code=500)

        except json.JSONDecodeError:
            _LOGGER.error(f"Invalid JSON in script output: {result.stdout}")
            return self.json({
                "error": "Invalid JSON in script output",
                "stdout": result.stdout
            }, status_code=500)
