"""Reglas declarativas para condiciones, variables locales y llamadas por ID."""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,63}\Z")
VALUE_LIMIT = 4096
MAX_DEPTH = 12
MAX_STEPS = 512
OPERATORS = {
    "eq": "Es igual a", "ieq": "Es igual a (sin distinguir mayúsculas)",
    "neq": "No es igual a", "contains": "Contiene",
    "gt": "Es mayor que (número)", "gte": "Es mayor o igual (número)",
    "lt": "Es menor que (número)", "lte": "Es menor o igual (número)",
    "exists": "Existe", "missing": "No existe",
}
NUMERIC_OPERATORS = {"gt", "gte", "lt", "lte"}
VALUELESS_OPERATORS = {"exists", "missing"}
REF_FIELDS = {"run_action": ("action_id",), "condition": ("then_id", "else_id")}


def _number(raw: str) -> Decimal | None:
    if not isinstance(raw, str) or len(raw) > 120:
        return None
    try:
        value = Decimal(raw.strip())
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def evaluate(key, op, expected, variables, *, expected_known=True):
    if not isinstance(op, str) or op not in OPERATORS:
        raise ValueError("Operador de condición desconocido.")
    if not isinstance(key, str) or not NAME.fullmatch(key):
        raise ValueError("Escribe un nombre de variable válido.")
    actual = variables.get(key)
    if op == "exists":
        return actual is not None
    if op == "missing":
        return actual is None
    if actual is None or not expected_known:
        return False
    if op == "eq":
        return actual == expected
    if op == "ieq":
        return actual.casefold() == expected.casefold()
    if op == "neq":
        return actual != expected
    if op == "contains":
        return bool(expected) and expected in actual
    lhs, rhs = _number(actual), _number(expected)
    if lhs is None or rhs is None:
        return False
    if op == "gt":
        return lhs > rhs
    if op == "gte":
        return lhs >= rhs
    if op == "lt":
        return lhs < rhs
    return lhs <= rhs


def references(steps):
    for step in steps:
        kind = step.get("type")
        for field in REF_FIELDS.get(kind, ()) if isinstance(kind, str) else ():
            ref = step.get(field)
            if isinstance(ref, str) and ref:
                yield ref


def validate_steps(steps):
    for step in steps:
        kind = step.get("type")
        if kind == "set_variable":
            key, value = step.get("key"), step.get("value", "")
            if not isinstance(key, str) or not NAME.fullmatch(key) or len(key) > 58:
                raise ValueError("Escribe un nombre de variable local (hasta 58 letras, números o guiones bajos).")
            if not isinstance(value, str) or len(value) > VALUE_LIMIT:
                raise ValueError("El valor de una variable admite hasta 4096 caracteres.")
        elif kind == "run_action":
            if not isinstance(step.get("action_id"), str) or not step["action_id"]:
                raise ValueError("Selecciona la acción que se reutilizará.")
        elif kind == "condition":
            key, op, value = step.get("key"), step.get("operator"), step.get("value", "")
            if not isinstance(key, str) or not NAME.fullmatch(key):
                raise ValueError("Escribe el nombre de la variable, sin llaves: por ejemplo, count o local_saludo.")
            if not isinstance(op, str) or op not in OPERATORS:
                raise ValueError("Selecciona un operador de comparación.")
            if not isinstance(value, str) or len(value) > VALUE_LIMIT:
                raise ValueError("La comparación admite hasta 4096 caracteres.")
            branches = [step.get(field, "") for field in REF_FIELDS[kind]]
            if not all(isinstance(branch, str) for branch in branches) or not any(branches):
                raise ValueError("Elige una acción para al menos uno de los resultados.")


def validate_links(action, actions):
    """Examina solo los enlaces del flujo editado, incluso las ramas no elegidas."""
    candidates = {item.id: item for item in actions}
    stack = [(action.id, iter(references(action.steps)))]
    visiting, visited = {action.id}, set()
    while stack:
        ident, links = stack[-1]
        target = next(links, None)
        if target is None:
            visited.add(ident)
            visiting.remove(ident)
            stack.pop()
            continue
        if target not in candidates:
            raise ValueError("Una subacción hace referencia a una acción que no existe.")
        if target in visiting:
            raise ValueError("Estas acciones se llamarían entre sí formando un ciclo.")
        if target not in visited:
            visiting.add(target)
            stack.append((target, iter(references(candidates[target].steps))))
