"""
Offline unit tests for the pure helpers in stats.opportunity — the SQL filter-clause
builder and the MySQL-type → native-Python converter. (The query functions themselves
are DB-backed and covered by app boot + manual radar checks, not here.)
"""
import datetime
import decimal

from jobs_intelligence_ai.services.stats.opportunity import _build_filter_clause, _native


def test_no_filters_returns_empty():
    """No filters → empty clause and no params."""
    assert _build_filter_clause(None) == ("", {})
    assert _build_filter_clause({}) == ("", {})


def test_single_value_filters():
    """Single state/portal/occ_group each produce one bound equality condition."""
    clause, params = _build_filter_clause({"state": "Wien"})
    assert "l.location = :f_state" in clause and params == {"f_state": "Wien"}
    clause, params = _build_filter_clause({"portal": "karriere.at"})
    assert "j.portal = :f_portal" in clause and params["f_portal"] == "karriere.at"
    clause, params = _build_filter_clause({"occ_group": "IT/EDV"})
    assert "j.occupational_group = :f_occ_group" in clause


def test_multi_value_filter_uses_in_clause():
    """A list of states becomes an IN (...) with one placeholder + param per value."""
    clause, params = _build_filter_clause({"states": ["Wien", "Tirol"]})
    assert "l.location IN (:f_state_0, :f_state_1)" in clause
    assert params == {"f_state_0": "Wien", "f_state_1": "Tirol"}


def test_min_salary_is_cast_and_int():
    """min_salary is coerced to int and compared via CAST; non-numeric is ignored."""
    clause, params = _build_filter_clause({"min_salary": "2000"})
    assert "CAST(j.salary AS DECIMAL(10,2)) >= :f_min_salary" in clause
    assert params["f_min_salary"] == 2000
    assert _build_filter_clause({"min_salary": "abc"}) == ("", {})


def test_combined_filters_join_with_and_prefix():
    """Multiple filters AND together and the whole clause starts with ' AND '."""
    clause, params = _build_filter_clause({"state": "Wien", "min_salary": 1500})
    assert clause.startswith(" AND ")
    assert "l.location = :f_state" in clause and "f_min_salary" in params


def test_native_converts_mysql_types():
    """Decimals collapse to int/float, dates become ISO strings, others pass through."""
    assert _native(decimal.Decimal("10")) == 10
    assert _native(decimal.Decimal("10.5")) == 10.5
    assert _native(datetime.date(2026, 6, 23)) == "2026-06-23"
    assert _native("karriere.at") == "karriere.at"
