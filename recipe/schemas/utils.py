import attr
import inspect
from six import string_types
from sqlalchemy import distinct, func
from sureberus import schema as S

SCALAR_TYPES = [S.Integer(), S.String(), S.Float(), S.Boolean()]


def _chain(*args):
    """Chain several coercers together"""

    def fn(value):
        for arg in args:
            value = arg(value)
        return value

    return fn


def _make_sqlalchemy_datatype_lookup():
    """ Build a dictionary of the allowed sqlalchemy casts """
    from sqlalchemy.sql import sqltypes

    d = {}
    for name in dir(sqltypes):
        sqltype = getattr(sqltypes, name)
        if name.lower() not in d and name[0] != "_" and name != "NULLTYPE":
            if inspect.isclass(sqltype) and issubclass(sqltype, sqltypes.TypeEngine):
                d[name.lower()] = sqltype
    return d


sqlalchemy_datatypes = _make_sqlalchemy_datatype_lookup()

format_lookup = {
    "comma": ",.0f",
    "dollar": "$,.0f",
    "percent": ".0%",
    "comma1": ",.1f",
    "dollar1": "$,.1f",
    "percent1": ".1%",
    "comma2": ",.2f",
    "dollar2": "$,.2f",
    "percent2": ".2%",
}


def coerce_format(v):
    return format_lookup.get(v, v)


aggregations = {
    "sum": func.sum,
    "min": func.min,
    "max": func.max,
    "avg": func.avg,
    "count": func.count,
    "count_distinct": lambda fld: func.count(distinct(fld)),
    "month": lambda fld: func.date_trunc("month", fld),
    "week": lambda fld: func.date_trunc("week", fld),
    "year": lambda fld: func.date_trunc("year", fld),
    "quarter": lambda fld: func.date_trunc("quarter", fld),
    "age": lambda fld: func.date_part("year", func.age(fld)),
    "none": lambda fld: fld,
    None: lambda fld: fld,
    # Percentile aggregations do not work in all engines
    "median": func.median,
    "percentile1": lambda fld: func.percentile_cont(0.01).within_group(fld),
    "percentile5": lambda fld: func.percentile_cont(0.05).within_group(fld),
    "percentile10": lambda fld: func.percentile_cont(0.10).within_group(fld),
    "percentile25": lambda fld: func.percentile_cont(0.25).within_group(fld),
    "percentile50": lambda fld: func.percentile_cont(0.50).within_group(fld),
    "percentile75": lambda fld: func.percentile_cont(0.75).within_group(fld),
    "percentile90": lambda fld: func.percentile_cont(0.90).within_group(fld),
    "percentile95": lambda fld: func.percentile_cont(0.95).within_group(fld),
    "percentile99": lambda fld: func.percentile_cont(0.99).within_group(fld),
}


def coerce_pop_version(shelf):
    shelf.pop("_version", None)
    return shelf
