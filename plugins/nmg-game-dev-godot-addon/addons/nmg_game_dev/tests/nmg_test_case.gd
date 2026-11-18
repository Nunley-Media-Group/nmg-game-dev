extends RefCounted
## Base class for the add-on's headless tests. run_tests.gd clears failures before each test_*
## method and counts the method as failed when any check recorded a failure.

var failures: Array[String] = []


func check(condition: bool, message: String) -> void:
	if not condition:
		failures.append(message)


func check_eq(actual: Variant, expected: Variant, label: String) -> void:
	if actual != expected:
		failures.append("%s: expected %s, got %s" % [label, var_to_str(expected), var_to_str(actual)])
