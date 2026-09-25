from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Moonraker is not accessed as a package on a printer,
    # but having access to the types is incredibly useful
    from moonraker.confighelper import ConfigHelper
    from moonraker.server import WebRequest


class Instrumentor:
    def __init__(self, config: ConfigHelper):
        config.get_server().register_endpoint(
            "/server/instrumentor/health", ["GET"], self.health_check
        )
        self.logger = logging.getLogger("moonraker.components.instrumentor")

        self.logger.info("Initialized")


    async def health_check(self, web_request: WebRequest):
        return {"state": "healthy"}


def load_component(config: ConfigHelper):
    return Instrumentor(config)
