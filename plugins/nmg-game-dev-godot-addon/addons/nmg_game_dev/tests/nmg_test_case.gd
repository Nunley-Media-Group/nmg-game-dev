extends RefCounted
## Base class for the add-on's headless tests. run_tests.gd gives each test_* method a fresh
## instance and counts the method as failed when any check recorded a failure or the engine logged
## an error while it ran.

var failures: Array[String] = []
## The runner's nmg_log_capture.gd logger; null when a test runs outside run_tests.gd.
var log_capture: Object = null


func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)


func check_eq(actual: Variant, expected: Variant, label: String) -> void:
	if actual != expected:
		failures.append("%s: expected %s, got %s" % [label, var_to_str(expected), var_to_str(actual)])


## Return and clear the warnings (push_warning and engine warnings) logged since the last call.
func take_warnings() -> PackedStringArray:
	if log_capture == null:
		failures.append("take_warnings needs run_tests.gd's log capture")
		return PackedStringArray()
	return log_capture.call("take_warnings")
