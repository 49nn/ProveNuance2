"""
solver/engine.py — silnik Datalog: bottom-up, stratified NAF, builtiny.

Obsługuje:
  - unifikację zmiennych (prefix '?')
  - ekspansję meets_condition/2 → inline required_facts z tabeli condition
  - builtiny: ge/2, gt/2, le/2, lt/2, eq/2, ne/2
  - stratified negation-as-failure (NAF)
  - bottom-up fixed-point evaluation

Ograniczenia (bezpieczeństwo Datalog):
  - Wszystkie zmienne w negowanych atomach muszą być uziemione przez
    wcześniejsze atomy pozytywne w tej samej regule (safe Datalog).
  - Builtiny wymagają uziemionych argumentów.
"""

from __future__ import annotations

import itertools
from typing import Iterator, Optional

from .types import Atom, Rule

# ---------------------------------------------------------------------------
# Builtiny
# ---------------------------------------------------------------------------

BUILTINS: frozenset[str] = frozenset({"ge", "gt", "le", "lt", "eq", "ne"})


def _eval_builtin(pred: str, args: tuple[str, ...]) -> bool:
    if len(args) != 2:
        return False
    a_raw, b_raw = args
    # Próba porównania numerycznego; fallback do string dla eq/ne
    try:
        a, b = float(a_raw), float(b_raw)
        return {
            "ge": a >= b,
            "gt": a > b,
            "le": a <= b,
            "lt": a < b,
            "eq": a == b,
            "ne": a != b,
        }[pred]
    except (ValueError, KeyError):
        if pred == "eq":
            return a_raw == b_raw
        if pred == "ne":
            return a_raw != b_raw
        return False


# ---------------------------------------------------------------------------
# Podstawienia (substitutions)
# ---------------------------------------------------------------------------

Substitution = dict[str, str]


def _walk(term: str, subst: Substitution) -> str:
    """Podąża łańcuchem podstawień dla zmiennej."""
    seen: set[str] = set()
    while term.startswith("?") and term in subst:
        if term in seen:
            break
        seen.add(term)
        term = subst[term]
    return term


def _apply(args: tuple[str, ...], subst: Substitution) -> tuple[str, ...]:
    return tuple(_walk(a, subst) for a in args)


def _unify(
    pattern: tuple[str, ...],
    ground:  tuple[str, ...],
    subst:   Substitution,
) -> Optional[Substitution]:
    """Unifikuje wzorzec z krotką uziemionych argumentów. Zwraca nowe podstawienie lub None."""
    if len(pattern) != len(ground):
        return None
    s = dict(subst)
    for p, g in zip(pattern, ground):
        p = _walk(p, s)
        g = _walk(g, s)
        if p == g:
            continue
        if p.startswith("?"):
            s[p] = g
        elif g.startswith("?"):
            s[g] = p
        else:
            return None  # clash stałych
    return s


# ---------------------------------------------------------------------------
# Ekspansja meets_condition/2
# ---------------------------------------------------------------------------

def _first_var(atoms: list[Atom]) -> Optional[str]:
    """Zwraca pierwszą zmienną ('?...') pojawiającą się w atomach (lewa strona)."""
    for atom in atoms:
        for arg in atom.args:
            if arg.startswith("?"):
                return arg
    return None


def _freshen(
    atoms:               list[Atom],
    entity_var:          str,
    replace_entity_with: str,
    counter:             int,
) -> list[Atom]:
    """
    Zwraca atomy z:
      - entity_var zastąpionym przez replace_entity_with
      - pozostałe '?'-zmienne przemianowane na ?VAR_mc<counter>
        (zapobieganie kolizjom zmiennych z różnych wywołań tego samego warunku)
    """
    result: list[Atom] = []
    for atom in atoms:
        new_args: list[str] = []
        for arg in atom.args:
            if not arg.startswith("?"):
                new_args.append(arg)
            elif arg == entity_var:
                new_args.append(replace_entity_with)
            else:
                new_args.append(f"{arg}_mc{counter}")
        result.append(Atom(pred=atom.pred, args=tuple(new_args), negated=atom.negated))
    return result


def expand_meets_condition(
    rules:      list[Rule],
    conditions: dict[str, list[Atom]],
) -> list[Rule]:
    """
    Zastępuje atomy meets_condition(E, cond_id) w ciałach reguł
    przez required_facts odpowiedniego warunku (z podstawieniem encji).

    Nieznane condition_id są pozostawiane bez zmian (solver zignoruje je).

    Args:
        rules:      lista reguł do transformacji
        conditions: słownik condition_id → list[Atom] (required_facts)

    Returns:
        Nowa lista reguł po ekspansji.
    """
    counter = itertools.count()
    expanded: list[Rule] = []

    for rule in rules:
        new_body: list[Atom] = []
        for atom in rule.body:
            if atom.pred == "meets_condition" and len(atom.args) == 2:
                entity_arg = atom.args[0]
                cond_id    = atom.args[1].strip("\"'")  # usuń ewentualne cudzysłowy
                if cond_id in conditions:
                    req_facts  = conditions[cond_id]
                    entity_var = _first_var(req_facts)
                    cnt        = next(counter)
                    if entity_var:
                        new_body.extend(_freshen(req_facts, entity_var, entity_arg, cnt))
                    else:
                        new_body.extend(req_facts)
                else:
                    new_body.append(atom)  # warunek nieznany — zostaw
            else:
                new_body.append(atom)

        expanded.append(Rule(
            rule_id=rule.rule_id,
            fragment_id=rule.fragment_id,
            head_pred=rule.head_pred,
            head_args=rule.head_args,
            body=new_body,
        ))

    return expanded


# ---------------------------------------------------------------------------
# Stratyfikacja
# ---------------------------------------------------------------------------

def _find_neg_cycle_preds(
    neg_deps: dict[str, set[str]],
    all_deps: dict[str, set[str]],
    preds:    set[str],
) -> set[str]:
    """
    Znajduje predykaty należące do cyklu przechodzącego przez negację.

    Cykl istnieje gdy p negatywnie zależy od q ORAZ q może dosięgnąć p
    przez dowolne zależności (pozytywne lub negatywne).
    """
    # Oblicz domknięcie przechodnie przez wszystkie zależności
    reachability: dict[str, set[str]] = {}

    def reachable(start: str) -> set[str]:
        if start in reachability:
            return reachability[start]
        visited: set[str] = set()
        stack = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            stack.extend(all_deps.get(node, set()))
        reachability[start] = visited
        return visited

    cycle_preds: set[str] = set()
    for p in preds:
        for q in neg_deps.get(p, set()):
            if p in reachable(q):
                cycle_preds.add(p)
                cycle_preds.add(q)
    return cycle_preds


def compute_strata(rules: list[Rule]) -> dict[str, int]:
    """
    Oblicza numer warstwy (stratum) dla każdego predykatu.

    Zasady:
      - stratum[p] >= stratum[q]     gdy p pozytywnie zależy od q
      - stratum[p] >  stratum[q]     gdy p negatywnie zależy od q (NAF)

    Podnosi ValueError gdy program nie jest stratyfikowalny
    (cykl przez negację).

    Returns:
        Słownik pred -> int (>= 0).
    """
    preds:    set[str]              = set()
    pos_deps: dict[str, set[str]]   = {}
    neg_deps: dict[str, set[str]]   = {}

    for rule in rules:
        p = rule.head_pred
        preds.add(p)
        pos_deps.setdefault(p, set())
        neg_deps.setdefault(p, set())
        for atom in rule.body:
            if atom.pred in BUILTINS:
                continue
            preds.add(atom.pred)
            if atom.negated:
                neg_deps[p].add(atom.pred)
            else:
                pos_deps[p].add(atom.pred)

    stratum: dict[str, int] = {p: 0 for p in preds}
    max_iter = len(preds) ** 2 + len(preds) + 2
    changed  = True
    iters    = 0

    while changed and iters < max_iter:
        changed = False
        iters  += 1
        for p in preds:
            # zależność pozytywna: stratum[p] >= stratum[dep]
            for dep in pos_deps.get(p, set()):
                dep_s = stratum.get(dep, 0)
                if stratum[p] < dep_s:
                    stratum[p] = dep_s
                    changed = True
            # zależność negatywna: stratum[p] > stratum[dep]
            for dep in neg_deps.get(p, set()):
                needed = stratum.get(dep, 0) + 1
                if stratum[p] < needed:
                    stratum[p] = needed
                    changed = True

    if iters >= max_iter:
        all_deps = {p: pos_deps.get(p, set()) | neg_deps.get(p, set()) for p in preds}
        cycle = _find_neg_cycle_preds(neg_deps, all_deps, preds)
        cycle_str = ", ".join(sorted(cycle)[:10])
        if len(cycle) > 10:
            cycle_str += f" … (+{len(cycle) - 10})"
        raise ValueError(
            f"Program nie jest stratyfikowalny — cykl przez negację (NAF). "
            f"Predykaty w cyklu: [{cycle_str}]."
        )

    return stratum


# ---------------------------------------------------------------------------
# Dopasowanie ciała reguły (backtracking)
# ---------------------------------------------------------------------------

Facts = dict[str, set[tuple[str, ...]]]


def _match_body(
    body:  list[Atom],
    facts: Facts,
    subst: Substitution,
    start: int = 0,
) -> Iterator[Substitution]:
    """
    Generator wszystkich podstawień rozszerzających subst,
    przy których ciało body (od indeksu start) jest prawdziwe w facts.

    Leniwa ewaluacja zamiast materializacji całej listy — zapobiega
    eksplozji pamięci dla reguł z wieloma pasującymi atomami (O(M^N)).
    Użycie indeksu start eliminuje O(N²) alokacje slicingu.

    Warunek bezpieczeństwa (safe Datalog):
      - argumenty negowanych atomów muszą być uziemione przez poprzednie
        pozytywne atomy — w przeciwnym razie gałąź jest pomijana (fail).
    """
    if start >= len(body):
        yield dict(subst)
        return

    atom = body[start]
    grounded = _apply(atom.args, subst)

    # Builtin
    if atom.pred in BUILTINS:
        if any(a.startswith("?") for a in grounded):
            return  # nie można wyznaczyć — pomiń
        ok = _eval_builtin(atom.pred, grounded)
        if ok != atom.negated:  # negated=True → chcemy False → ok must be False
            yield from _match_body(body, facts, subst, start + 1)
        return

    # NAF — wszystkie args muszą być uziemione
    if atom.negated:
        if any(a.startswith("?") for a in grounded):
            # Niebezpieczna negacja: zmienna niezwiązana — pomiń tę gałąź
            # (nie możemy ocenić not P(?X) gdy ?X nieznane; konserwatywnnie: fail)
            return
        pred_facts = facts.get(atom.pred, set())
        if grounded not in pred_facts:
            yield from _match_body(body, facts, subst, start + 1)
        return

    # Pozytywny atom — szukamy pasujących faktów
    for fact_args in facts.get(atom.pred, set()):
        new_subst = _unify(atom.args, fact_args, subst)
        if new_subst is not None:
            yield from _match_body(body, facts, new_subst, start + 1)


# ---------------------------------------------------------------------------
# Bezpieczne porządkowanie ciała reguły
# ---------------------------------------------------------------------------

def _safe_reorder_body(body: list[Atom]) -> list[Atom]:
    """
    Przesuwa negowane atomy i builtiny na koniec ciała reguły.

    Kolejność: pozytywne (wiążą zmienne) → builtiny → negacje.
    Dzięki temu wszystkie zmienne w negowanych atomach są uziemione
    przez wcześniejsze pozytywne atomy (safe Datalog).
    """
    positive  = [a for a in body if not a.negated and a.pred not in BUILTINS]
    builtins  = [a for a in body if not a.negated and a.pred in BUILTINS]
    negations = [a for a in body if a.negated]
    return positive + builtins + negations


# ---------------------------------------------------------------------------
# Ewaluator bottom-up
# ---------------------------------------------------------------------------

# Maksymalna liczba iteracji fixed-point dla jednej warstwy stratyfikacji.
# Czysty Datalog zawsze zbiega (skończona baza Herbranda), ale błędne reguły
# lub niespodziewane dane mogą powodować nieskończone pętle — stąd zabezpieczenie.
_MAX_STRATUM_ITERS = 100_000


class Evaluator:
    """
    Główny silnik solvera Datalog z stratified NAF.

    Użycie::

        ev = Evaluator(rules, edb_facts, conditions)
        all_facts = ev.evaluate()
        results   = ev.query("auction", ("?O",))
    """

    def __init__(
        self,
        rules:      list[Rule],
        facts:      Facts,
        conditions: dict[str, list[Atom]],
    ) -> None:
        # 1. Ekspansja meets_condition/2
        expanded = expand_meets_condition(rules, conditions)

        # 2. Bezpieczne porządkowanie: pozytywne → builtiny → negacje
        for rule in expanded:
            rule.body = _safe_reorder_body(rule.body)

        # 3. Oblicz stratyfikację
        self._strata: dict[str, int] = compute_strata(expanded)

        # 4. Zachowaj reguły i fakty
        self._rules: list[Rule] = expanded
        self._facts: Facts      = {k: set(v) for k, v in facts.items()}

    # ------------------------------------------------------------------

    def evaluate(self) -> Facts:
        """
        Uruchamia ewaluację bottom-up (po warstwach, fixed-point w każdej).

        Returns:
            Słownik pred -> set[tuple[...]] ze wszystkimi faktami (EDB + IDB).
        """
        max_stratum = max(self._strata.values(), default=0)

        for s in range(max_stratum + 1):
            stratum_rules = [r for r in self._rules if self._strata.get(r.head_pred, 0) == s]
            self._eval_stratum(stratum_rules)

        return dict(self._facts)

    def _eval_stratum(self, rules: list[Rule]) -> None:
        """Fixed-point dla jednej warstwy stratyfikacji."""
        changed = True
        iters = 0
        while changed:
            if iters >= _MAX_STRATUM_ITERS:
                raise ValueError(
                    f"Fixed-point nie zbiegł po {_MAX_STRATUM_ITERS} iteracjach — "
                    f"możliwy błąd w regułach lub nieskończony cykl pochodnych."
                )
            changed = False
            iters += 1
            for rule in rules:
                for subst in _match_body(rule.body, self._facts, {}):
                    grounded_head = _apply(rule.head_args, subst)
                    if any(a.startswith("?") for a in grounded_head):
                        continue  # głowa nie uziemiona — pomiń
                    pred_facts = self._facts.setdefault(rule.head_pred, set())
                    if grounded_head not in pred_facts:
                        pred_facts.add(grounded_head)
                        changed = True

    # ------------------------------------------------------------------

    def query(
        self,
        goal_pred: str,
        goal_args: tuple[str, ...],
    ) -> list[dict[str, str]]:
        """
        Zapytaj o cel goal_pred(goal_args) w derivowanych faktach.

        Args:
            goal_pred: nazwa predykatu
            goal_args: krotka argumentów (zmienne '?X' lub stałe)

        Returns:
            Lista podstawień (dict var->value) spełniających cel.
            Pusta lista gdy cel jest fałszywy.
        """
        results: list[dict[str, str]] = []
        for fact_args in self._facts.get(goal_pred, set()):
            subst = _unify(goal_args, fact_args, {})
            if subst is not None:
                results.append(subst)
        return results

    @property
    def strata(self) -> dict[str, int]:
        return dict(self._strata)
