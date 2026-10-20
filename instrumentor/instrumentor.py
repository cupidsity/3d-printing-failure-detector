from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

try:
    import jurigged

    watcher = jurigged.watch(str(Path(__file__).resolve()))
except ImportError:
    pass

if TYPE_CHECKING:
    # Moonraker is not accessed as a package on a printer,
    # but having access to the types is incredibly useful
    from moonraker.components.klippy_apis import KlippyAPI
    from moonraker.components.webcam import WebcamManager
    from moonraker.confighelper import ConfigHelper
    from moonraker.server import WebRequest


class Instrumentor:
    def __init__(self, config: ConfigHelper):
        self.server = config.get_server()
        self.webcams: WebcamManager = self.server.lookup_component("webcam")
        self.klippy_apis: KlippyAPI = self.server.lookup_component("klippy_apis")
        self.logger = logging.getLogger("moonraker.components.instrumentor")

        self.server.register_endpoint(
            "/server/instrumentor/health", ["GET"], self.health_check
        )
        self.server.register_endpoint(
            "/server/instrumentor/events", ["GET"], self.list_events
        )
        self.server.register_endpoint(
            "/server/instrumentor/objects", ["GET"], self.get_printer_objects
        )
        self.server.register_endpoint(
            "/server/instrumentor/gcode", ["GET"], self.gcode_stats
        )
        self.server.register_endpoint(
            "/server/instrumentor/position", ["GET"], self.position_stats
        )
        self.server.register_endpoint(
            "/server/instrumentor/webcam", ["GET"], self.webcam_snapshot
        )

        self.logger.info("Initialized")

    async def health_check(self, web_request: WebRequest):
        return {"state": "healthy"}

    async def list_events(self, web_request: WebRequest):
        return list(self.server.events.keys()).sort()

    async def get_printer_objects(self, web_request: WebRequest):
        objects = await self.klippy_apis.get_object_list()

        # `name: None` gets all fields of the object
        requested_objects = {name: None for name in objects}

        return await self.klippy_apis.query_objects(requested_objects)

    async def gcode_stats(self, web_request: WebRequest):
        return await self.klippy_apis.query_objects(
            {
                "print_stats": ["info"],
                "virtual_sdcard": [
                    "file_path",
                    "is_active",
                    "file_position",
                    "file_size",
                ],
            }
        )

    async def position_stats(self, web_request: WebRequest):
        # toolhead->position: commanded position, where it should be
        # gcode_move->position: where it is after offsets
        # Both are given in [x, y, z, extruder]
        return await self.klippy_apis.query_objects(
            {"toolhead": ["position"], "gcode_move": ["position"]}
        )

    async def webcam_snapshot(self, web_request: WebRequest):
        cameras = []

        for name, webcam in self.webcams.get_webcams().items():
            cameras.append(
                {
                    "name": name,
                    "snapshot_url": webcam.snapshot_url,
                    "flip_horizontal": webcam.flip_horizontal,
                    "flip_vertical": webcam.flip_vertical,
                    "rotation": webcam.rotation,
                }
            )

        return cameras


def load_component(config: ConfigHelper):
    return Instrumentor(config)
