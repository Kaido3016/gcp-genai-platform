import pytest

from app.core.exceptions import ToolExecutionError
from app.services.agent.tools.calculator_tool import safe_arithmetic_eval


def test_basic_arithmetic():
    assert safe_arithmetic_eval("2 + 3") == 5
    assert safe_arithmetic_eval("(3 + 4) * 2") == 14
    assert safe_arithmetic_eval("10 / 4") == 2.5
    assert safe_arithmetic_eval("2 ** 8") == 256
    assert safe_arithmetic_eval("-5 + 2") == -3


def test_rejects_non_arithmetic_syntax():
    with pytest.raises(ToolExecutionError):
        safe_arithmetic_eval("__import__('os').system('echo pwned')")


def test_rejects_name_references():
    with pytest.raises(ToolExecutionError):
        safe_arithmetic_eval("os.system('ls')")


def test_rejects_function_calls():
    with pytest.raises(ToolExecutionError):
        safe_arithmetic_eval("open('/etc/passwd').read()")


def test_rejects_invalid_syntax():
    with pytest.raises(ToolExecutionError):
        safe_arithmetic_eval("2 +")
