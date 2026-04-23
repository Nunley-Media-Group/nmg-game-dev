from __future__ import annotations

import bpy


class NmgGameDevPipelineProps(bpy.types.PropertyGroup):
    variant: bpy.props.StringProperty(  # type: ignore[valid-type]
        name="Active variant",
        description="Desktop | Mobile",
        default="",
    )

    preset: bpy.props.EnumProperty(  # type: ignore[valid-type]
        name="Active preset",
        description="Quality preset for pipeline operations",
        items=(
            ("STANDARD", "Standard", "Default quality preset"),
            ("HERO", "Hero", "Character-tier preset"),
        ),
        default="STANDARD",
    )
