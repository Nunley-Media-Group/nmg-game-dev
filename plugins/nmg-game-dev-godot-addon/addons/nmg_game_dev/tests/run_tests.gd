extends SceneTree
## Headless test runner for the nmg_game_dev add-on.
##
## Run as: godot --headless --path <project> -s res://addons/nmg_game_dev/tests/run_tests.gd
## Loads every tests/test_*.gd beside this script, calls each test_* method on a fresh instance,
## prints one PASS/FAIL line per method and then "N passed, M failed". Exits 1 on any failure, or
## when no test ran.

const TEST_PREFIX: String = "test_"


func _initialize() -> void:
	var tests_dir: String = (get_script() as Script).resource_path.get_base_dir()
	var passed: int = 0
	var failed: int = 0
	for file_name: String in _test_files(tests_dir):
		var script: GDScript = load(tests_dir.path_join(file_name)) as GDScript
		if script == null:
			print("FAIL %s: could not load the script" % file_name)
			failed += 1
			continue
		for method_name: String in _test_methods(script):
			var instance: Object = script.new()
			instance.call(method_name)
			var failures: Array = instance.get("failures")
			if failures.is_empty():
				passed += 1
				print("PASS %s::%s" % [file_name, method_name])
			else:
				failed += 1
				print("FAIL %s::%s" % [file_name, method_name])
				for message: Variant in failures:
					print("    %s" % message)
	print("%d passed, %d failed" % [passed, failed])
	quit(1 if failed > 0 or passed == 0 else 0)


func _test_files(tests_dir: String) -> PackedStringArray:
	var files: PackedStringArray = PackedStringArray()
	for file_name: String in DirAccess.get_files_at(tests_dir):
		if file_name.begins_with(TEST_PREFIX) and file_name.get_extension() == "gd":
			files.append(file_name)
	files.sort()
	return files


func _test_methods(script: GDScript) -> PackedStringArray:
	var names: PackedStringArray = PackedStringArray()
	for method: Dictionary in script.get_script_method_list():
		var method_name: String = method["name"]
		if method_name.begins_with(TEST_PREFIX) and not names.has(method_name):
			names.append(method_name)
	names.sort()
	return names
