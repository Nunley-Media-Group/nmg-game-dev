class_name NmgVersionLabel
extends Label
## A Label that shows the running build's version, such as "v1.3.0" (#254).
##
## The label reads NmgBuild.version() once, when it enters the tree, and shows prefix followed by
## the version. A build that declares no version shows nothing. It has no per-frame hook.

## Text placed before the version. Set it to "" to show the bare version.
@export var prefix: String = "v"


func _ready() -> void:
	var version: String = NmgBuild.version()
	text = prefix + version if not version.is_empty() else ""
