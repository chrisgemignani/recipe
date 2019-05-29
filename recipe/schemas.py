"""
Registers recipe schemas
"""

import inspect
import logging
import re

from sqlalchemy import distinct, func
from sureberus import schema as S

from recipe.compat import basestring

logging.captureWarnings(True)


def _make_sqlalchemy_datatype_lookup():
    """ Build a dictionary of the allowed sqlalchemy casts """
    from sqlalchemy.sql import sqltypes
    d = {}
    for name in dir(sqltypes):
        sqltype = getattr(sqltypes, name)
        if name.lower() not in d and name[0] != '_' and name != 'NULLTYPE':
            if inspect.isclass(sqltype) and issubclass(
                sqltype, sqltypes.TypeEngine
            ):
                d[name.lower()] = sqltype
    return d


sqlalchemy_datatypes = _make_sqlalchemy_datatype_lookup()

format_lookup = {
    'comma': ',.0f',
    'dollar': '$,.0f',
    'percent': '.0%',
    'comma1': ',.1f',
    'dollar1': '$,.1f',
    'percent1': '.1%',
    'comma2': ',.2f',
    'dollar2': '$,.2f',
    'percent2': '.2%',
}

default_aggregation = 'sum'
no_aggregation = 'none'
aggregations = {
    'sum': func.sum,
    'min': func.min,
    'max': func.max,
    'avg': func.avg,
    'count': func.count,
    'count_distinct': lambda fld: func.count(distinct(fld)),
    'month': lambda fld: func.date_trunc('month', fld),
    'week': lambda fld: func.date_trunc('week', fld),
    'year': lambda fld: func.date_trunc('year', fld),
    'quarter': lambda fld: func.date_trunc('quarter', fld),
    'age': lambda fld: func.date_part('year', func.age(fld)),
    'none': lambda fld: fld,
    None: lambda fld: fld,
}

aggr_keys = '|'.join(
    k for k in aggregations.keys() if isinstance(k, basestring)
)
# Match patterns like sum(a)
field_pattern = re.compile(r'^({})\((.*)\)$'.format(aggr_keys))


def find_operators(value):
    """ Find operators in a field that may look like "a+b-c" """
    parts = re.split('[+-\/\*]', value)
    field, operators = parts[0], []
    if len(parts) == 1:
        return field, operators

    remaining_value = value[len(field):]
    if remaining_value:
        for part in re.findall('[+-\/\*][\w\.]+', remaining_value):
            # TODO: Full validation on other fields
            other_field = _coerce_string_into_field(
                part[1:], search_for_operators=False
            )
            operators.append({'operator': part[0], 'field': other_field})
    return field, operators


def _coerce_string_into_field(value, search_for_operators=True):
    """ Convert a string into a field, potentially parsing a functional
    form into a value and aggregation """
    if isinstance(value, basestring):
        # Remove all whitespace
        value = re.sub(r'\s+', '', value, flags=re.UNICODE)
        m = re.match(field_pattern, value)
        if m:
            aggr, value = m.groups()
            operators = []
            if search_for_operators:
                value, operators = find_operators(value)
            result = {'value': value, 'aggregation': aggr}
            if operators:
                result['operators'] = operators
            return result

        else:
            operators = []
            if search_for_operators:
                value, operators = find_operators(value)

            # Check for a number
            try:
                float(value)
                result = {'value': value, '_use_raw_value': True}
            except ValueError:
                result = {'value': value}
            if operators:
                result['operators'] = operators
            return result
    else:
        return value


def _field_post(field):
    """Add sqlalchemy conversion helper info

    Convert aggregation -> _aggregation_fn,
    as -> _cast_to_datatype and
    default -> _coalesce_to_value"""
    field['_aggregation_fn'] = aggregations.get(field['aggregation'])

    if 'as' in field:
        field['_cast_to_datatype'] = sqlalchemy_datatypes.get(field.pop('as'))

    if 'default' in field:
        field['_coalesce_to_value'] = field.pop('default')

    return field


def _to_lowercase(value):
    if isinstance(value, basestring):
        return value.lower()
    else:
        return value


def _field_schema(aggr=True, required=True):
    """Make a field schema that either aggregates or doesn't. """
    if aggr:
        ag = S.String(
            required=False,
            allowed=list(aggregations.keys()),
            default=default_aggregation,
            nullable=True
        )
    else:
        ag = S.String(
            required=False,
            allowed=[no_aggregation, None],
            default=no_aggregation,
            nullable=True
        )

    operator = S.Dict({
        'operator': S.String(allowed=['+', '-', '/', '*']),
        'field': S.String()
    })

    return S.Dict(
        schema={
            'value':
                S.String(),
            'aggregation':
                ag,
            'condition':
                'condition',
            'operators':
                S.List(schema=operator, required=False),
            # Performs a dividebyzero safe sql division
            'divide_by':
                S.Dict(required=False, schema='aggregated_field'),
            # Performs casting
            'as':
                S.String(
                    required=False,
                    allowed=list(sqlalchemy_datatypes.keys()),
                    coerce=_to_lowercase
                ),
            # Performs coalescing
            'default': {
                'anyof': [S.Integer(),
                          S.String(),
                          S.Float(),
                          S.Boolean()],
                'required': False
            },
            # Should the value be used directly in sql
            '_use_raw_value':
                S.Boolean(required=False)
        },
        coerce=_coerce_string_into_field,
        coerce_post=_field_post,
        allow_unknown=False,
        required=required,
    )


class ConditionPost(object):
    """ Convert an operator like 'gt', 'lt' into '_op' and '_op_value'
    for easier parsing into SQLAlchemy """

    def __init__(self, operator, _op, scalar):
        self.operator = operator
        self._op = _op
        self.scalar = scalar

    def __call__(self, value):
        value['_op'] = self._op
        _op_value = value.get(self.operator)
        # Wrap in a list
        if not self.scalar:
            if not isinstance(_op_value, list):
                _op_value = [_op_value]
        value['_op_value'] = _op_value
        value.pop(self.operator)
        return value


def _condition_schema(operator, _op, scalar=True, aggr=False):
    if scalar:
        allowed_values = [S.Integer(), S.String(), S.Float(), S.Boolean()]
    else:
        allowed_values = [
            S.Integer(),
            S.String(),
            S.Float(),
            S.Boolean(),
            S.List(),
        ]

    if aggr:
        field = 'aggregated_field'
    else:
        field = 'non_aggregated_field'

    _condition_schema = S.Dict(
        allow_unknown=False,
        schema={'field': field,
                operator: {
                    'anyof': allowed_values
                }},
        coerce_post=ConditionPost(operator, _op, scalar)
    )
    return _condition_schema


def _full_condition_schema(aggr=False):
    """ Conditions can be a field with an operator, like this yaml example

    condition:
        field: foo
        gt: 22

    Or conditions can be a list of and-ed and or-ed conditions

    condition:
        or:
            - field: foo
              gt: 22
            - field: foo
              lt: 0

    :param aggr: Build the condition with aggregate fields (default is False)
    """

    # Handle conditions where there's an operator
    operator_condition = S.DictWhenKeyExists({
        'gt': _condition_schema('gt', '__gt__', aggr=aggr),
        'gte': _condition_schema('gte', '__ge__', aggr=aggr),
        'ge': _condition_schema('ge', '__ge__', aggr=aggr),
        'lt': _condition_schema('lt', '__lt__', aggr=aggr),
        'lte': _condition_schema('lte', '__le__', aggr=aggr),
        'le': _condition_schema('le', '__le__', aggr=aggr),
        'eq': _condition_schema('eq', '__eq__', aggr=aggr),
        'ne': _condition_schema('ne', '__ne__', aggr=aggr),
        'in': _condition_schema('in', 'in_', scalar=False, aggr=aggr),
        'notin': _condition_schema('notin', 'notin', scalar=False, aggr=aggr),
        'or': S.Dict(schema={
            'or': S.List(schema='condition')
        }),
        'and': S.Dict(schema={
            'and': S.List(schema='condition')
        }),
    },
                                             required=False)

    return {
        'registry': {
            'condition': operator_condition,
            'aggregated_field': _field_schema(aggr=True),
            'non_aggregated_field': _field_schema(aggr=False),
        },
        'schema_ref': 'condition',
    }


def _move_extra_fields(value):
    """ Move any fields that look like "{role}_field" into the extra_fields
    list. These will be processed as fields. Rename them as {role}_expression.
    """
    if isinstance(value, dict):
        keys_to_move = [k for k in value.keys() if k.endswith('_field')]
        if keys_to_move:
            value['extra_fields'] = []
            for k in keys_to_move:
                value['extra_fields'].append({
                    'name': k[:-6] + '_expression',
                    'field': value.pop(k)
                })

    return value


def _adjust_kinds(value):
    if isinstance(value, dict):
        if 'kind' not in value:
            value['kind'] = 'Metric'

        if value.get('kind') == 'IdValueDimension':
            value['kind'] = 'Dimension'

        if value.get('kind') == 'Dimension':
            value['kind'] == 'Dimension'

        if value.get('kind') == 'DivideMetric':
            value['kind'] == 'Metric'
            value['field'] = value.pop('numerator_field')
            value['divide_by'] = value.pop('denominator_field')

        if value.get('kind') == 'WtdAvgMetric':
            value['kind'] == 'Metric'
            fld = value.pop('field')
            wt = value.pop('weight')
            # assumes both field and weight are strings
            value['field'] = '{}*{}'.format(fld, wt)
            value['divide_by'] = wt

    return value


condition_schema = _full_condition_schema(aggr=False)

quickfilter_schema = S.List(
    required=False,
    schema=S.Dict(
        schema={
            'condition': 'condition',
            'name': S.String(required=True)
        }
    )
)

# Create a full schema that uses a registry
ingredient_schema = S.DictWhenKeyIs(
    'kind',
    {
        'Metric':
            S.Dict(
                allow_unknown=True,
                schema={
                    'field':
                        'aggregated_field',
                    'divide_by':
                        'optional_aggregated_field',
                    'format':
                        S.String(
                            coerce=lambda v: format_lookup.get(v, v),
                            required=False
                        ),
                    'quickfilters':
                        quickfilter_schema
                }
            ),
        'Dimension':
            S.Dict(
                allow_unknown=True,
                coerce=_move_extra_fields,
                schema={
                    'field':
                        'non_aggregated_field',
                    'extra_fields':
                        S.List(
                            required=False,
                            schema=S.Dict(
                                schema={
                                    'field': 'non_aggregated_field',
                                    'name': S.String(required=True)
                                }
                            )
                        ),
                    'format':
                        S.String(
                            coerce=lambda v: format_lookup.get(v, v),
                            required=False
                        ),
                    'quickfilters':
                        quickfilter_schema
                },
            ),
        'Filter':
            S.Dict(allow_unknown=True, schema={
                'condition': 'condition'
            }),
        'Having':
            S.Dict(
                allow_unknown=True, schema={
                    'condition': 'having_condition'
                }
            )
    },
    # If the kind can't be found, default to metric
    default_choice='Metric',
    coerce=_adjust_kinds,
    registry={
        'aggregated_field': _field_schema(aggr=True),
        'optional_aggregated_field': _field_schema(aggr=True, required=False),
        'non_aggregated_field': _field_schema(aggr=False),
        'condition': _full_condition_schema(aggr=False),
        'having_condition': _full_condition_schema(aggr=True),
    }
)

shelf_schema = S.Dict(
    valueschema=ingredient_schema, keyschema=S.String(), allow_unknown=True
)

# This schema is used with sureberus
recipe_schema = S.Dict(
    schema={
        'metrics':
            S.List(schema=S.String(), required=False),
        'dimensions':
            S.List(schema=S.String(), required=False),
        'filters':
            S.List(
                schema={'oneof': [S.String(), 'condition']}, required=False
            ),
        'order_by':
            S.List(schema=S.String(), required=False),
    },
    registry={
        'aggregated_field': _field_schema(aggr=True),
        'optional_aggregated_field': _field_schema(aggr=True, required=False),
        'non_aggregated_field': _field_schema(aggr=False),
        'condition': _full_condition_schema(aggr=False),
        'having_condition': _full_condition_schema(aggr=True),
    }
)
