extends "res://addons/nmg_game_dev/tests/nmg_test_case.gd"
## NmgBuild.version() and the NmgVersionLabel node (#254). Each test restores the version setting.

const VERSION_SETTING: String = "application/config/version"


func test_version_reads_the_project_setting() -> void:
	var original: Variant = ProjectSettings.get_setting(VERSION_SETTING, "")
	ProjectSettings.set_setting(VERSION_SETTING, "1.3.0")
	check_eq(NmgBuild.version(), "1.3.0", "version() after the setting changes")
	ProjectSettings.set_setting(VERSION_SETTING, original)


func test_version_is_empty_without_a_setting() -> void:
	var original: Variant = ProjectSettings.get_setting(VERSION_SETTING, "")
	ProjectSettings.set_setting(VERSION_SETTING, "")
	check_eq(NmgBuild.version(), "", "version() with no version declared")
	ProjectSettings.set_setting(VERSION_SETTING, original)


func test_version_matches_the_running_project() -> void:
	var declared: String = str(ProjectSettings.get_setting(VERSION_SETTING, ""))
	check_eq(NmgBuild.version(), declared, "version() against the project setting")


func test_version_label_shows_the_prefixed_version() -> void:
	var original: Variant = ProjectSettings.get_setting(VERSION_SETTING, "")
	ProjectSettings.set_setting(VERSION_SETTING, "1.3.0")
	var default_text: String = await _label_text("v")
	check_eq(default_text, "v1.3.0", "label with the default prefix")
	var bare_text: String = await _label_text("")
	check_eq(bare_text, "1.3.0", "label with an empty prefix")
	var custom_text: String = await _label_text("Build ")
	check_eq(custom_text, "Build 1.3.0", "label with a custom prefix")
	ProjectSettings.set_setting(VERSION_SETTING, original)


func test_version_label_is_empty_without_a_version() -> void:
	var original: Variant = ProjectSettings.get_setting(VERSION_SETTING, "")
	ProjectSettings.set_setting(VERSION_SETTING, "")
	var shown: String = await _label_text("v")
	check_eq(shown, "", "label with no version declared")
	ProjectSettings.set_setting(VERSION_SETTING, original)


func test_version_label_defaults_its_prefix_to_v() -> void:
	var label: NmgVersionLabel = NmgVersionLabel.new()
	check_eq(label.prefix, "v", "default prefix")
	label.free()


## Add an NmgVersionLabel with prefix to the root, let a frame pass so its _ready runs, then return
## the text it set and free it. Like test_nmg_launch.gd, the test waits for the frame.
func _label_text(prefix: String) -> String:
	var tree: SceneTree = Engine.get_main_loop() as SceneTree
	var label: NmgVersionLabel = NmgVersionLabel.new()
	label.prefix = prefix
	tree.root.add_child(label)
	await tree.process_frame
	var shown: String = label.text
	tree.root.remove_child(label)
	label.free()
	return shown
