from enum import StrEnum
from typing import TYPE_CHECKING, Callable, Coroutine

if TYPE_CHECKING:
    from moonraker.server import Server, WebRequest


class Methods(StrEnum):
    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"


class HTTPManager:
    def __init__(self, server: Server):
        self.server = server

    def add_route(
        self,
        route: str,
        methods: list[Methods],
        callback: Callable[[WebRequest], Coroutine],
    ):
        """
        Register an endpoint to Moonraker's Tornado webserver

        Routes must begin with /server, /printer, /machine, or /debug (mandated by Moonraker).

        The callback must return a JSON-serializable value, and the endpoint responds with
        `{"result": <value>}`
        """

        if not route.startswith("/"):
            route = "/" + route

        if route.split("/")[1] not in ("server", "printer", "machine", "debug"):
            raise ValueError(
                f"Invalid route passed: `{route}`. It must start with /server, /printer, /machine, or /debug."
            )

        self.server.register_endpoint(
            route,
            [method.value for method in methods],
            callback,
            ["http"],
        )

    async def fetch(self):
        raise NotImplementedError
