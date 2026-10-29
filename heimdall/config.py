from configparser import ConfigParser
from pathlib import Path


class Config:
    def __init__(self, path: str | Path) -> None:
        self.path = path
        self.parser = ConfigParser()

        self.parser.read(path)

    def get(self, path: str, default: str | None = None):
        """
        Get a string value from the config.

        path: The "path" of the value, given as `"section.key"`.
        default: The fallback value if the key is not found.
        """

        return self.parser.get(*self._split(path), fallback=default)

    def get_float(self, path: str, default: float | None = None):
        "Same as `.get`, but returns a float"
        return self.parser.getfloat(*self._split(path), fallback=default)

    def get_bool(self, path: str, default: bool | None = None):
        "Same as `.get`, but returns a boolean"
        return self.parser.getboolean(*self._split(path), fallback=default)

    def set(self, path: str, value: str):
        """
        Set a string value for the config.

        path: The "path" of the value, given as `"section.key"`.
        value: The value to set
        """

        self.parser.set(*self._split(path), value)

        with open(self.path) as f:
            self.parser.write(f)

    def set_float(self, path: str, value: float):
        "Same as `.set`, but takes a float"
        self.set(path, str(value))

    def set_bool(self, path: str, value: bool):
        "Same as `.set`, but takes a bool"
        self.set(path, "true" if value else "false")

    @staticmethod
    def _split(path: str) -> tuple[str, str]:
        parts = path.split(".")

        if len(parts) != 2:
            raise NameError(
                f"Config path `{path}` does not map to a valid section and key!"
            )

        return (parts[0], parts[1])
