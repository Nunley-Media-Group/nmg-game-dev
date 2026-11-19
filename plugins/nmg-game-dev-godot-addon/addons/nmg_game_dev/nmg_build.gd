class_name NmgBuild
extends RefCounted
## The version of the running build (#254).
##
## /ship writes the version it ships into application/config/version in game/project.godot, and into
## every export preset's version fields, so the build reports the version it was shipped as:
##     var shown: String = NmgBuild.version()    # "1.3.0"
## It is a static helper; it needs no autoload and no per-frame work.

const VERSION_SETTING: String = "application/config/version"


## Return the version of the running build, or "" when the project declares none.
static func version() -> String:
	return str(ProjectSettings.get_setting(VERSION_SETTING, ""))
