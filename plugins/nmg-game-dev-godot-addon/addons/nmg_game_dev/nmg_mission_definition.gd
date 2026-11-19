class_name NmgMissionDefinition
extends Resource
## One mission from the design backlog, scaffolded by /design into game/missions/<Name>.tres.

## The mission's display name.
@export var mission_name: String = ""
## The act the mission belongs to.
@export var act: int = 0
## The region (level) the mission plays in.
@export var region: StringName = &""
## Missions that must be complete before this one unlocks.
@export var depends_on: Array[StringName] = []
## The design doc that describes the mission, relative to the consumer project root.
@export var design_doc_path: String = ""
