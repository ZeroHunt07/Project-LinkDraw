"""Safe evaluation of spreadsheet-style arithmetic formulas."""
import ast
import operator
import re


_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}
_UNARY_OPERATORS = {ast.UAdd: operator.pos, ast.USub: operator.neg}
_CELL_PATTERN = re.compile(r"^[A-Z]{1,3}[1-9][0-9]*$")
_RANGE_PATTERN = re.compile(r"\b([A-Z]{1,3}[1-9][0-9]*):([A-Z]{1,3}[1-9][0-9]*)\b")


def _column_number(label):
    value = 0
    for char in label:
        value = value * 26 + ord(char) - ord("A") + 1
    return value


def _range_cells(start, end):
    start_col, start_row = re.fullmatch(r"([A-Z]+)([0-9]+)", start).groups()
    end_col, end_row = re.fullmatch(r"([A-Z]+)([0-9]+)", end).groups()
    c1, c2 = _column_number(start_col), _column_number(end_col)
    r1, r2 = int(start_row), int(end_row)
    if abs(c2 - c1) > 256 or abs(r2 - r1) > 10000:
        raise ValueError("Formula range is too large")
    columns = range(min(c1, c2), max(c1, c2) + 1)
    rows = range(min(r1, r2), max(r1, r2) + 1)
    if len(columns) * len(rows) > 10000:
        raise ValueError("Formula range is too large")

    def column_label(number):
        chars = []
        while number:
            number, remainder = divmod(number - 1, 26)
            chars.append(chr(ord("A") + remainder))
        return "".join(reversed(chars))

    return [f"{column_label(col)}{row}" for row in rows for col in columns]


def evaluate_cell(address, cells, cache=None, stack=None):
    """Evaluate one cell value or formula, detecting invalid and cyclic references."""
    cache = {} if cache is None else cache
    stack = set() if stack is None else stack
    address = address.upper()
    if address in cache:
        return cache[address]
    if address in stack:
        raise ValueError(f"Circular reference involving {address}")
    raw = str(cells.get(address, "")).strip()
    if not raw:
        return 0
    if len(raw) > 4096:
        raise ValueError(f"Formula in {address} is too long")
    if not raw.startswith("="):
        try:
            return float(raw)
        except ValueError:
            return raw

    stack.add(address)
    try:
        source = raw[1:].upper()
        source = source.replace("^", "**")
        source = _RANGE_PATTERN.sub(r'RANGE("\1","\2")', source)
        tree = ast.parse(source, mode="eval")
        result = _evaluate(tree.body, cells, cache, stack)
        cache[address] = result
        return result
    except (SyntaxError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(f"Invalid formula in {address}: {exc}") from exc
    finally:
        stack.remove(address)


def _evaluate(node, cells, cache, stack):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.Name):
        if not _CELL_PATTERN.fullmatch(node.id):
            raise ValueError(f"Unknown cell or name: {node.id}")
        return evaluate_cell(node.id, cells, cache, stack)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARY_OPERATORS:
        return _UNARY_OPERATORS[type(node.op)](_evaluate(node.operand, cells, cache, stack))
    if isinstance(node, ast.BinOp) and type(node.op) in _BINARY_OPERATORS:
        left = _evaluate(node.left, cells, cache, stack)
        right = _evaluate(node.right, cells, cache, stack)
        if isinstance(node.op, ast.Pow) and isinstance(right, (int, float)) and abs(right) > 1000:
            raise ValueError("Formula exponent is too large")
        return _BINARY_OPERATORS[type(node.op)](left, right)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        if node.keywords:
            raise ValueError("Formula functions do not accept named arguments")
        if name == "RANGE" and len(node.args) == 2:
            first, last = node.args
            if not (isinstance(first, ast.Constant) and isinstance(first.value, str)
                    and isinstance(last, ast.Constant) and isinstance(last.value, str)):
                raise ValueError("Invalid range")
            return [
                evaluate_cell(cell, cells, cache, stack)
                for cell in _range_cells(first.value, last.value)
            ]
        if name == "RANGE":
            raise ValueError("Invalid range")
        if name not in {"SUM", "AVERAGE", "MIN", "MAX", "COUNT", "ABS", "ROUND", "SQRT"}:
            raise ValueError(f"Unsupported function: {name}")
        values = [_evaluate(arg, cells, cache, stack) for arg in node.args]
        flattened = []
        for value in values:
            flattened.extend(value if isinstance(value, list) else [value])
        numeric = [float(value) for value in flattened if isinstance(value, (int, float))]
        functions = {
            "SUM": lambda: sum(numeric),
            "AVERAGE": lambda: sum(numeric) / len(numeric) if numeric else 0,
            "MIN": lambda: min(numeric) if numeric else 0,
            "MAX": lambda: max(numeric) if numeric else 0,
            "COUNT": lambda: len(numeric),
            "ABS": lambda: abs(float(values[0])) if len(values) == 1 else _arity(name),
            "ROUND": lambda: round(float(values[0]), int(values[1]) if len(values) > 1 else 0)
            if 1 <= len(values) <= 2 else _arity(name),
            "SQRT": lambda: float(values[0]) ** 0.5 if len(values) == 1 else _arity(name),
        }
        if name not in functions:
            raise ValueError(f"Unsupported function: {name}")
        return functions[name]()
    raise ValueError("Formula contains an unsupported operation")


def _arity(name):
    raise ValueError(f"Invalid arguments for {name}")
