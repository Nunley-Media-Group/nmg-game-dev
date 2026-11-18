extends "res://addons/nmg_game_dev/tests/nmg_test_case.gd"
## NmgMissionDefinition: the exported fields /design writes into game/missions/<Name>.tres.

const MissionScript: GDScript = preload("res://addons/nmg_game_dev/nmg_mission_definition.gd")


func test_defaults() -> void:
	var mission: Resource = MissionScript.new()
	check_eq(mission.get("mission_name"), "", "mission_name")
	check_eq(mission.get("act"), 0, "act")
	check_eq(mission.get("region"), &"", "region")
	check_eq((mission.get("depends_on") as Array).size(), 0, "depends_on")
	check_eq(mission.get("design_doc_path"), "", "design_doc_path")


func test_fields_are_exported_for_storage() -> void:
	var expected: Dictionary = {
		"mission_name": TYPE_STRING,
		"act": TYPE_INT,
		"region": TYPE_STRING_NAME,
		"depends_on": TYPE_ARRAY,
		"design_doc_path": TYPE_STRING,
	}
	var found: Dictionary = {}
	for property: Dictionary in MissionScript.new().get_property_list():
		if expected.has(property["name"]):
			check(
				(int(property["usage"]) & PROPERTY_USAGE_STORAGE) != 0,
				"%s is not stored" % property["name"],
			)
			check(
				(int(property["usage"]) & PROPERTY_USAGE_EDITOR) != 0,
				"%s is not shown in the editor" % property["name"],
			)
			check_eq(int(property["type"]), expected[property["name"]], "%s type" % property["name"])
			found[property["name"]] = true
	check_eq(found.size(), expected.size(), "exported field count")


func test_depends_on_is_typed_string_names() -> void:
	var mission: Resource = MissionScript.new()
	var depends: Array = mission.get("depends_on")
	check(depends.is_typed(), "depends_on is not a typed array")
	check_eq(depends.get_typed_builtin(), TYPE_STRING_NAME, "depends_on element type")


func test_round_trips_through_a_tres() -> void:
	var mission: Resource = MissionScript.new()
	mission.set("mission_name", "Opening")
	mission.set("act", 1)
	mission.set("region", &"Harbor")
	var depends: Array[StringName] = [&"Prologue"]
	mission.set("depends_on", depends)
	mission.set("design_doc_path", "docs/design/missions/opening.md")
	var path: String = "user://nmg_mission_round_trip.tres"
	check_eq(ResourceSaver.save(mission, path), OK, "save")
	var loaded: Resource = ResourceLoader.load(path, "", ResourceLoader.CACHE_MODE_IGNORE)
	check(loaded != null, "the saved mission did not load")
	if loaded != null:
		check_eq(loaded.get("mission_name"), "Opening", "mission_name")
		check_eq(loaded.get("act"), 1, "act")
		check_eq(loaded.get("region"), &"Harbor", "region")
		check_eq(loaded.get("depends_on"), depends, "depends_on")
		check_eq(loaded.get("design_doc_path"), "docs/design/missions/opening.md", "design_doc_path")
	DirAccess.remove_absolute(ProjectSettings.globalize_path(path))
