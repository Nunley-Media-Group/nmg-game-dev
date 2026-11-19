extends Logger
## Collects the engine's errors and warnings for run_tests.gd while it is registered with
## OS.add_logger. Errors (script, shader, and engine) fail the running test; warnings, such as
## push_warning, are handed to the test through NmgTestCase.take_warnings().

var _mutex: Mutex = Mutex.new()
var _errors: PackedStringArray = PackedStringArray()
var _warnings: PackedStringArray = PackedStringArray()


func _log_error(
	_function: String,
	file: String,
	line: int,
	code: String,
	rationale: String,
	_editor_notify: bool,
	error_type: int,
	_script_backtraces: Array[ScriptBacktrace],
) -> void:
	var text: String = code if rationale.is_empty() else "%s: %s" % [code, rationale]
	_mutex.lock()
	if error_type == ERROR_TYPE_WARNING:
		_warnings.append(text)
	else:
		_errors.append("%s (%s:%d)" % [text, file, line])
	_mutex.unlock()


func _log_message(_message: String, _error: bool) -> void:
	pass


## Return and clear the errors logged since the last call.
func take_errors() -> PackedStringArray:
	_mutex.lock()
	var taken: PackedStringArray = _errors
	_errors = PackedStringArray()
	_mutex.unlock()
	return taken


## Return and clear the warnings logged since the last call.
func take_warnings() -> PackedStringArray:
	_mutex.lock()
	var taken: PackedStringArray = _warnings
	_warnings = PackedStringArray()
	_mutex.unlock()
	return taken
