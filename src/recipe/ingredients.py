from uuid import uuid4

from sqlalchemy import Float, between, case, cast, distinct, func

from recipe.compat import basestring
from recipe.exceptions import BadIngredient
from recipe.utils import AttrDict


# TODO: How do we avoid attaching significance to particular
# indices in columns

# Should dimensions having ids be an extension to recipe?


class Ingredient(object):
    """ Ingredients combine to make a SQLAlchemy query.
    """

    def __init__(self, **kwargs):
        """ Initializing an instance of the Ingredient Class

        :param columns: A list of SQLAlchemy columns to use in a query.
        :type *ColumnElement: list
        :param filters: A list of SQLAlchemy BinaryExpressions to use in the
                        .filter() clause of a query.
        :type *BinaryExpressions: list
        :param havings: A list of SQLAlchemy BinaryExpressions to use in the
                        .filter() clause of a query.
        :type *BinaryExpressions: list
        :param group_by: A list of SQLAlchemy columns to use in the group_by
                        clause of a query
        :param formatters: A list of callables to apply to the result values
        :type *callables: list
        :param ordering: The default ordering of this ingredient if it is
        used in a ``recipe.order_by``
        """
        self.id = kwargs.pop('id', uuid4().hex[:12])
        self.columns = kwargs.pop('columns', [])
        self.filters = kwargs.pop('filters', [])
        self.havings = kwargs.pop('havings', [])
        self.group_by = kwargs.pop('group_by', [])
        self.formatters = kwargs.pop('formatters', [])
        self.column_suffixes = kwargs.pop('column_suffixes', None)
        self.anonymize = False
        # What order should this be in
        self.ordering = kwargs.pop('ordering', 'asc')

        if not isinstance(self.formatters, (list, tuple)):
            raise BadIngredient('formatters passed to an ingredient must be a '
                                'list or tuple')
        # If explicit suffixes are passed in, there must be one for each column
        if self.column_suffixes is not None and \
                len(self.column_suffixes) != len(self.columns):
            raise BadIngredient('column_suffixes must be the same length as '
                                'columns')

        # Any remaining passed properties are available in self.meta
        self.meta = AttrDict(kwargs)

    def describe(self):
        return u'({}){} {}'.format(self.__class__.__name__, self.id,
                                   ' '.join(
                                       unicode(col) for col in self.columns))

    def _format_value(self, value):
        """ Formats value using any stored formatters
        """
        for f in self.formatters:
            # TODO: Add anonymizer caching
            value = f(value)
        return value

    def make_column_suffixes(self):
        """ Make sure we have the right column suffixes. These will be appended
        to `id` when generating the query.
        """
        if self.column_suffixes:
            return self.column_suffixes

        if len(self.columns) == 0:
            return ()

        elif len(self.columns) == 1:
            if self.formatters:
                return ('_raw',)
            else:
                return ('',)
        else:
            raise BadIngredient('column_suffixes must be supplied if there is '
                                'more than one column')

    @property
    def query_columns(self):
        """ Yield labeled columns to be used as a select in a query
        """
        for column, suffix in zip(self.columns, self.make_column_suffixes()):
            yield column.label(self.id + suffix)

    @property
    def cauldron_extras(self):
        """ Yield extra tuples containing a field name and a callable that takes
        a row
        """
        if self.formatters:
            raw_property = self.id + '_raw'
            yield self.id, lambda row: \
                self._format_value(getattr(row, raw_property))

    def __cmp__(self, other):
        """ Make ingredients sortable.
        """
        return cmp(self.id, other.id)

    def build_filter(self, value, operator=None):
        """ Builds a filter based on a supplied value and optional operator. If
        no operator is supplied an ``in`` filter will be used for a list and a
        ``eq`` filter if we get a scalar value

        :param value: The value to use in the filter
        :type value: object
        :param operator: An operator to override the default interaction
        :type operator: str
        """
        scalar_ops = ['ne', 'lt', 'lte', 'gt', 'gte', 'eq']
        non_scalar_ops = ['notin', 'between', 'in']
        is_scalar = False
        if isinstance(value, (int, basestring)):
            is_scalar = True

        filter_column = self.columns[0]

        if is_scalar:
            if operator not in scalar_ops and operator is not None:
                raise ValueError('This is not a valid operator for the '
                                 'supplied value')
            if operator == 'ne':
                return Filter(filter_column != value)
            if operator == 'lt':
                return Filter(filter_column < value)
            if operator == 'lte':
                return Filter(filter_column <= value)
            if operator == 'gt':
                return Filter(filter_column > value)
            if operator == 'gte':
                return Filter(filter_column >= value)
            return Filter(filter_column == value)
        else:
            if operator not in non_scalar_ops and operator is not None:
                raise ValueError('This is not a valid operator for the '
                                 'supplied value.')
            if operator == 'notin':
                return Filter(filter_column.notin_(value))
            if operator == 'between':
                if len(value) != 2:
                    ValueError('When using between, you can only supply a '
                               'lower and upper bounds.')
                lower_bound, upper_bound = value
                return Filter(between(filter_column, lower_bound,
                                      upper_bound))
            return Filter(filter_column.in_(value))

    @property
    def expression(self):
        """ An accessor for the sqlalchemy expression representing this
        Ingredient """
        if self.columns:
            return self.columns[0]
        else:
            return None


class Filter(Ingredient):
    """ A simple filter created from a single expression.
    """

    def __init__(self, expression, **kwargs):
        super(Filter, self).__init__(**kwargs)
        self.filters = [expression]

    def __cmp__(self, other):
        return cmp(unicode(self.filters[0]), unicode(other.filters[0]))

    def __repr__(self):
        return '{}'.format([unicode(f) for f in self.filters])

    def describe(self):
        """ Stringify this ingredient to help in debugging. """
        return u'({}){} {}'.format(self.__class__.__name__,
                                   self.id,
                                   unicode(self))

    @property
    def expression(self):
        """ An accessor for the sqlalchemy expression representing this
        Ingredient """
        if self.filters:
            return self.filters[0]
        else:
            return None


class Having(Ingredient):
    """ A Having that limits results based on an aggregate boolean clause
    """

    def __init__(self, expression, **kwargs):
        super(Having, self).__init__(**kwargs)
        self.havings = [expression]

    def __cmp__(self, other):
        return cmp(unicode(self.havings[0]), unicode(other.havings[0]))

    def __repr__(self):
        return u'{}'.format([unicode(f) for f in self.havings])

    def describe(self):
        """ Stringify this ingredient to help in debugging. """
        return u'({}){} {}'.format(self.__class__.__name__,
                                   self.id,
                                   unicode(self))

    @property
    def expression(self):
        """ An accessor for the sqlalchemy expression representing this
        Ingredient """
        if self.havings:
            return self.havings[0]
        else:
            return None


class Dimension(Ingredient):
    """ A simple dimension created from a single expression and optional
    id_expression
    """

    def __init__(self, expression, **kwargs):
        super(Dimension, self).__init__(**kwargs)
        id_expression = kwargs.pop('id_expression', expression)
        if id_expression is not expression:
            self.columns = [id_expression, expression]
            self.group_by = [id_expression, expression]
        else:
            self.columns = [expression]
            self.group_by = [expression]

    @property
    def cauldron_extras(self):
        """ Yield extra tuples containing a field name and a callable that takes
        a row
        """
        for extra in super(Dimension, self).cauldron_extras:
            yield extra

        if self.formatters:
            prop = self.id + '_raw'
        else:
            prop = self.id_prop

        yield self.id + '_id', lambda row: getattr(row, prop)

    @property
    def id_prop(self):
        """ The label of this dimensions id in the query columns """
        if len(self.columns) == 1:
            return self.id
        else:
            return self.id + '_id'


class IdValueDimension(Dimension):
    def __init__(self, id_expression, value_expression, **kwargs):
        kwargs['id_expression'] = id_expression
        super(IdValueDimension, self).__init__(value_expression, **kwargs)


class LookupDimension(Dimension):
    """ Returns the expression value looked up in a lookup dictionary
    """

    def __init__(self, expression, lookup, **kwargs):
        super(LookupDimension, self).__init__(expression, **kwargs)
        self.lookup = lookup
        if not isinstance(lookup, dict):
            raise BadIngredient("lookup for LookupDimension must be a "
                                "dictionary")
        self.default = kwargs.pop('default', 'Not found')
        self.formatters.insert(0,
                               lambda value: self.lookup.get(value,
                                                             self.default))


class Metric(Ingredient):
    """ A simple metric created from a single expression
    """

    def __init__(self, expression, **kwargs):
        super(Metric, self).__init__(**kwargs)
        self.columns = [expression]


class DivideMetric(Metric):
    """ A metric that divides a numerator by a denominator handling several
    possible error conditions

    The default strategy is to add an small value to the denominator
    Passing ifzero allows you to give a different value if the denominator is
    zero.
    """

    def __init__(self, numerator, denominator, **kwargs):
        ifzero = kwargs.pop('ifzero', 'epsilon')
        epsilon = kwargs.pop('epsilon', 0.000000001)
        if ifzero == 'epsilon':
            # Add an epsilon value to denominator to avoid divide by zero
            # errors
            expression = cast(numerator, Float) / (
                func.coalesce(cast(denominator, Float), 0.0) + epsilon)
        else:
            # If the denominator is zero, return the ifzero value otherwise do
            # the division
            expression = case(
                ((cast(denominator, Float) == 0.0, ifzero),),
                else_=cast(numerator, Float) / cast(denominator, Float))
        super(DivideMetric, self).__init__(expression, **kwargs)


class SumIfMetric(Metric):
    """ A metric that calculates a sum of an expression if a condition is true
    """

    def __init__(self, condition, expression, **kwargs):
        expression = func.sum(
            case(
                ((condition, expression),),
                else_=None
            ))

        super(SumIfMetric, self).__init__(expression, **kwargs)


class CountIfMetric(Metric):
    """ A metric that calculates a sum of an expression if a condition is true
    """

    def __init__(self, condition, expression, **kwargs):
        """ Initializes an instance of a CountIfMetric
        :param count_distinct: Should the count include a distinct
                               (default is True)
        """
        count_distinct = kwargs.pop('count_distinct', True)
        # Generate a case statement to perform the count
        inner_expr = case(((condition, expression),), else_=None)
        if count_distinct:
            inner_expr = distinct(inner_expr)
        super(CountIfMetric, self).__init__(func.count(inner_expr), **kwargs)
