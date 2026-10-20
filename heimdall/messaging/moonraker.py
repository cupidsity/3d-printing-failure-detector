import aiohttp
import io

from PIL import Image
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from moonraker.server import Server
    from moonraker.components.webcam import WebcamManager
    from moonraker.components.klippy_apis import KlippyAPI


class MoonRequester:
    def __init__(self, server: Server):
        self.server = server
        self.webcams: WebcamManager = self.server.lookup_component("webcam")
        self.klippy_apis: KlippyAPI = self.server.lookup_component("klippy_apis")

        self.client_session = aiohttp.ClientSession()
        ...

    async def get_camera_snapshot(self, webcam_name: str):
        webcam = self.webcams.get_webcams().get(webcam_name)

        if webcam is None:
            # Possibly throw an error?
            return

        # Normalize url path
        url = await webcam.get_snapshot_url()
        if not url.startswith("http"):
            if not url.startswith("/"):
                url = "/" + url

            url = "http://localhost" + url

        async with self.client_session.get("url") as response:
            # Need to check reponse code to make sure it worked
            img_bytes = await response.read()

        image = Image.open(io.BytesIO(img_bytes))

        # Do needed transformations

        if webcam.flip_horizontal:
            image = image.transpose(Image.Transpose.FLIP_LEFT_RIGHT)
        if webcam.flip_vertical:
            image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)

        match webcam.rotation:
            # Rotations can only be 90deg amounts, also no fallthrough
            case 90:
                image = image.transpose(Image.Transpose.ROTATE_90)
            case 180:
                image = image.transpose(Image.Transpose.ROTATE_180)
            case 270:
                image = image.transpose(Image.Transpose.ROTATE_270)
            case _:
                pass

        return image

    async def get_position(self):
        positions = await self.klippy_apis.query_objects(
            {"toolhead": ["position"], "gcode_move": ["position"]}
        )

        current = {
            "x": positions["gcode_move"][0],
            "y": positions["gcode_move"][1],
            "z": positions["gcode_move"][2],
            "extruder": positions["gcode_move"][3],
        }

        target = {
            "x": positions["toolhead"][0],
            "y": positions["toolhead"][1],
            "z": positions["toolhead"][2],
            "extruder": positions["toolhead"][3],
        }

        return {"current": current, "target": target}

    async def get_gcode_info(self):
        objects = await self.klippy_apis.query_objects(
            {
                "virtual_sdcard": [
                    "file_path",
                    "is_active",
                    "file_position",
                    "file_size",
                ],
            }
        )

        if not objects["virtual_sdcard"].pop("is_active"):
            return None

        return objects

    async def pause_print(self):
        await self.klippy_apis.pause_print()

    async def resume_print(self):
        await self.klippy_apis.resume_print()

    async def cancel_print(self):
        await self.klippy_apis.cancel_print()
