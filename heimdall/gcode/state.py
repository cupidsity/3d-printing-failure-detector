"""State transitions for the supported G-code positioning model."""

from __future__ import annotations

from dataclasses import dataclass, field
import math


@dataclass(slots=True)
class MachineState:
    """Mutable interpreter state required to resolve motion commands."""

    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    feed_rate: float = 0.0
    unit_scale: float = 1.0
    xyz_absolute: bool = True
    e_absolute_override: bool | None = None
    active_tool: int = 0
    e_positions: dict[int, float] = field(default_factory=lambda: {0: 0.0})
    filament_diameters: dict[int, float] = field(default_factory=dict)
    flow_percent: dict[int, float] = field(default_factory=lambda: {0: 100.0})
    volumetric_tools: set[int] = field(default_factory=set)
    plane: str = "XY"

    @property
    # Function: xyz
    # Groups the current machine coordinates into one point.
    #
    # Inputs:
    # * self: MachineState
    #
    # Output: The current X, Y, and Z coordinates.
    def xyz(self) -> tuple[float, float, float]:
        return self.x, self.y, self.z

    @property
    # Function: e_absolute
    # Resolves the active extrusion mode from its override and positioning mode.
    #
    # Inputs:
    # * self: MachineState
    #
    # Output: True when extrusion values are absolute.
    def e_absolute(self) -> bool:
        if self.e_absolute_override is not None:
            return self.e_absolute_override
        return self.xyz_absolute

    @property
    # Function: current_e
    # Gets or initializes the extrusion position for the active tool.
    #
    # Inputs:
    # * self: MachineState
    #
    # Output: The active tool's extrusion position.
    def current_e(self) -> float:
        return self.e_positions.setdefault(self.active_tool, 0.0)

    @property
    # Function: current_flow
    # Gets or initializes the flow percentage for the active tool.
    #
    # Inputs:
    # * self: MachineState
    #
    # Output: The active tool's flow percentage.
    def current_flow(self) -> float:
        return self.flow_percent.setdefault(self.active_tool, 100.0)

    # Function: set_active_tool
    # Selects a tool and initializes its independent extrusion settings.
    #
    # Inputs:
    # * self: MachineState
    # * tool: int
    # * default_filament_diameter: float
    #
    # Output: None.
    def set_active_tool(self, tool: int, default_filament_diameter: float) -> None:
        if tool < 0:
            raise ValueError("tool index cannot be negative")
        self.active_tool = tool
        self.e_positions.setdefault(tool, 0.0)
        self.flow_percent.setdefault(tool, 100.0)
        self.filament_diameters.setdefault(tool, default_filament_diameter)

    # Function: scale_linear
    # Converts a linear G-code value into millimeters.
    #
    # Inputs:
    # * self: MachineState
    # * value: float
    #
    # Output: The scaled linear value.
    def scale_linear(self, value: float) -> float:
        return value * self.unit_scale

    # Function: scale_extrusion
    # Converts linear or volumetric extrusion into millimeter-based units.
    #
    # Inputs:
    # * self: MachineState
    # * value: float
    #
    # Output: The scaled extrusion value.
    def scale_extrusion(self, value: float) -> float:
        power = 3 if self.active_tool in self.volumetric_tools else 1
        return value * (self.unit_scale**power)

    # Function: resolve_destination
    # Resolves optional axis words against the active positioning mode.
    #
    # Inputs:
    # * self: MachineState
    # * parameters: dict[str, float]
    #
    # Output: The destination X, Y, and Z coordinates.
    def resolve_destination(
        self, parameters: dict[str, float]
    ) -> tuple[float, float, float]:
        values = {"X": self.x, "Y": self.y, "Z": self.z}
        for axis in values:
            if axis not in parameters:
                continue
            scaled = self.scale_linear(parameters[axis])
            values[axis] = scaled if self.xyz_absolute else values[axis] + scaled
        return values["X"], values["Y"], values["Z"]

    # Function: resolve_extrusion_delta
    # Calculates deposited or retracted extrusion for a command.
    #
    # Inputs:
    # * self: MachineState
    # * parameters: dict[str, float]
    #
    # Output: The signed extrusion change.
    def resolve_extrusion_delta(self, parameters: dict[str, float]) -> float:
        if "E" not in parameters:
            return 0.0
        value = self.scale_extrusion(parameters["E"])
        return value - self.current_e if self.e_absolute else value

    # Function: apply_move
    # Commits a resolved motion command to the machine state.
    #
    # Inputs:
    # * self: MachineState
    # * destination: tuple[float, float, float]
    # * parameters: dict[str, float]
    #
    # Output: None.
    def apply_move(
        self, destination: tuple[float, float, float], parameters: dict[str, float]
    ) -> None:
        self.x, self.y, self.z = destination
        if "E" in parameters:
            value = self.scale_extrusion(parameters["E"])
            self.e_positions[self.active_tool] = (
                value if self.e_absolute else self.current_e + value
            )
        if "F" in parameters:
            self.feed_rate = self.scale_linear(parameters["F"])

    # Function: apply_g92
    # Applies a coordinate or extruder position reset.
    #
    # Inputs:
    # * self: MachineState
    # * parameters: dict[str, float]
    #
    # Output: None.
    def apply_g92(self, parameters: dict[str, float]) -> None:
        for axis in ("X", "Y", "Z"):
            if axis in parameters:
                setattr(self, axis.lower(), self.scale_linear(parameters[axis]))
        if "E" in parameters:
            self.e_positions[self.active_tool] = self.scale_extrusion(parameters["E"])

    # Function: filament_area
    # Calculates the active tool's filament cross-sectional area.
    #
    # Inputs:
    # * self: MachineState
    # * default_filament_diameter: float
    #
    # Output: The filament area in square millimeters.
    def filament_area(self, default_filament_diameter: float) -> float:
        diameter = self.filament_diameters.get(
            self.active_tool, default_filament_diameter
        )
        return math.pi * (diameter / 2.0) ** 2

