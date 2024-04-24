import ast
from _ast import Attribute, BoolOp, Call, Compare, Constant, Name
from datetime import datetime
from inspect import getsource
from typing import Any, Callable, Dict, List, TypeVar, Union

T = TypeVar("T")


def to_sql(predicate: Callable[[T], bool], properties: Dict[str, str]) -> str:
    class LambdaFinder(ast.NodeVisitor):
        def __init__(self, expression: Any) -> None:
            super().__init__()

            self.freevars: Dict[str, Any] = {}

            # Check globals.
            for name in expression.__code__.co_names:
                if name in expression.__globals__:
                    self.freevars[name] = expression.__globals__[name]

            # Capture closure variables.
            closure = expression.__closure__
            if closure:
                for name, value in zip(
                    expression.__code__.co_freevars, [x.cell_contents for x in closure]
                ):
                    self.freevars[name] = value

            line = getsource(expression).strip()

            if line.endswith(":"):
                line = f"{line}\n    pass"

            self.visit(ast.parse(line))

        def visit_Lambda(self, node: ast.Lambda) -> Any:  # pylint: disable-all
            self.expression = node

        @staticmethod
        def find(expression: Any):  # pylint: disable-all
            visitor = LambdaFinder(expression)
            return visitor.expression, visitor.freevars

    class LambdaVisitor(ast.NodeVisitor):
        def __init__(self, expression: ast.expr, freevars: Dict[str, Any]) -> None:
            super().__init__()
            self._expressions: List[Union[LambdaVisitor, str]] = []
            self._freevars = freevars
            self.visit(expression)

        def visit_Attribute(self, node: Attribute) -> Any:
            attr = node.attr
            value: Any = node.value
            if value.id in self._freevars:
                self._expressions.append(
                    self._get_sql_value(getattr(self._freevars[value.id], attr))
                )
            else:
                self._expressions.append(properties[attr])

        def visit_BoolOp(self, node: BoolOp) -> Any:
            self._expressions.append("(")
            expressions: List[Union[LambdaVisitor, str]] = []
            for value in node.values:
                expressions.append(LambdaVisitor(value, self._freevars))
                expressions.append(self._convert_op(node.op))
            expressions.pop()
            self._expressions.extend(expressions)
            self._expressions.append(")")

        def visit_Call(self, node: Call) -> Any:
            if not hasattr(node.func, "attr"):
                self.generic_visit(node)
                return
            attr = node.func.attr  # type: ignore
            if attr == "startswith":
                field_name = properties[node.func.value.attr]  # type: ignore
                self._expressions.append(
                    f"{field_name} LIKE '{self._get_value(node.args[0])}%'"
                )
            elif attr == "endswith":
                field_name = properties[node.func.value.attr]  # type: ignore
                self._expressions.append(
                    f"{field_name} LIKE '%{self._get_value(node.args[0])}'"
                )

        def visit_Compare(self, node: Compare) -> Any:
            op = node.ops[0]
            if isinstance(op, ast.In):
                field_name = properties[node.comparators[0].attr]  # type: ignore
                self._expressions.append(
                    f"{field_name} LIKE '%{self._get_value(node.left)}%'"
                )
            else:
                self._expressions.append(LambdaVisitor(node.left, self._freevars))
                self._expressions.append(self._convert_op(node.ops[0]))
                self._expressions.append(
                    LambdaVisitor(node.comparators[0], self._freevars)
                )

        def visit_Constant(self, node: Constant) -> Any:
            self._expressions.append(self._get_sql_value(node.value))

        def visit_Name(self, node: Name) -> Any:
            self._expressions.append(self._get_sql_value(self._freevars[node.id]))

        def _get_sql_value(self, value: Any) -> str:
            if value is None:
                return "NULL"
            if isinstance(value, str):
                return f"'{value}'"
            if isinstance(value, datetime):
                return f"timestamp '{value:%Y-%m-%d %H:%M:%S}'"
            return str(value)

        def _get_value(self, node: Any) -> Any:
            return self._freevars[node.id] if isinstance(node, Name) else node.value

        def _convert_op(self, op: Any) -> str:
            if isinstance(op, ast.And):
                return "AND"
            if isinstance(op, ast.Or):
                return "OR"
            if isinstance(op, ast.Is):
                return "IS"
            if isinstance(op, ast.IsNot):
                return "IS NOT"
            if isinstance(op, ast.Eq):
                return "="
            if isinstance(op, ast.NotEq):
                return "<>"
            if isinstance(op, ast.Gt):
                return ">"
            if isinstance(op, ast.GtE):
                return ">="
            if isinstance(op, ast.Lt):
                return "<"
            if isinstance(op, ast.LtE):
                return "<="
            return type(op).__name__

        def to_sql(self) -> str:
            text = ""
            for e in self._expressions:
                text += e.to_sql() if isinstance(e, LambdaVisitor) else f" {e}"
            return text

    # Find the lambda expression and any free variables encapsulated in it.
    expression, freevars = LambdaFinder.find(predicate)

    # Generate a where clause.
    where_clause = LambdaVisitor(expression, freevars).to_sql().strip()

    return where_clause
