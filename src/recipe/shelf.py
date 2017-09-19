from copy import copy
from sqlalchemy import Float
from sqlalchemy import Integer
from sqlalchemy import String
from sqlalchemy import func
from sqlalchemy.util import lightweight_named_tuple
from yaml import safe_load

from recipe import BadRecipe, Ingredient, BadIngredient
from recipe import Dimension
from recipe import Metric
from recipe.compat import basestring
from recipe.ingredients import ingredient_from_dict, alchemify
from recipe.utils import AttrDict


class Shelf(AttrDict):
    """ Holds ingredients used by a recipe

    Args:


    Returns:
        A Shelf object
    """

    class Meta:
        anonymize = False
        table = None

    def __init__(self, *args, **kwargs):
        super(Shelf, self).__init__(*args, **kwargs)

        self.Meta.ingredient_order = []
        self.Meta.table = kwargs.pop('table', None)

        # Set the ids of all ingredients on the shelf to the key
        for k, ingredient in self.items():
            ingredient.id = k

    def get(self, k, d=None):
        ingredient = super(Shelf, self).get(k, d)
        if isinstance(ingredient, Ingredient):
            ingredient.id = k
            ingredient.anonymize = self.Meta.anonymize
        return ingredient

    def __getitem__(self, key):
        """ Set the id and anonymize property of the ingredient whenever we
        get or set items """
        ingredient = super(Shelf, self).__getitem__(key)
        ingredient.id = key
        ingredient.anonymize = self.Meta.anonymize
        return ingredient

    def __setitem__(self, key, ingredient):
        """ Set the id and anonymize property of the ingredient whenever we
        get or set items """
        ingredient_copy = copy(ingredient)
        ingredient_copy.id = key
        ingredient_copy.anonymize = self.Meta.anonymize
        super(Shelf, self).__setitem__(key, ingredient_copy)

    def ingredients(self):
        """ Return the ingredients in this shelf in a deterministic order """
        return sorted(list(self.values()))

    @property
    def dimension_ids(self):
        return tuple(d.id for d in self.values() if
                     isinstance(d, Dimension))

    @property
    def metric_ids(self):
        return tuple(d.id for d in self.values() if
                     isinstance(d, Metric))

    @property
    def dimension_ids(self):
        """ Return the Dimensions on this shelf in the order in which
        they were used."""
        return tuple(
            sorted(
                [d.id for d in self.values()
                 if isinstance(d, Dimension)],
                key=lambda id: self.Meta.ingredient_order.index(id) \
                    if id in self.Meta.ingredient_order else 9999
            )
        )

    @property
    def metric_ids(self):
        """ Return the Metrics on this shelf in the order in which
        they were used. """
        return tuple(
            sorted(
                [d.id for d in self.values()
                 if isinstance(d, Metric)],
                key=lambda id: self.Meta.ingredient_order.index(id) \
                    if id in self.Meta.ingredient_order else 9999
            )
        )

    def __repr__(self):
        """ A string representation of the ingredients used in a recipe
        ordered by Dimensions, Metrics, Filters, then Havings
        """
        lines = []
        # sort the ingredients by type
        for ingredient in sorted(self.values()):
            lines.append(ingredient.describe())
        return '\n'.join(lines)

    def use(self, ingredient):
        # Track the order in which ingredients are added.
        self.Meta.ingredient_order.append(ingredient.id)
        self[ingredient.id] = ingredient

    @classmethod
    def from_yaml(cls, yaml_str, table):
        obj = safe_load(yaml_str)
        tablename = table.__name__
        locals()[tablename] = table

        d = {}
        for k, v in obj.iteritems():
            expr = v.get('expression')
            if isinstance(expr, basestring):
                v['expression'] = eval(alchemify(expr, tablename))
            elif isinstance(expr, list):
                v['expression'] = [eval(alchemify(stmt, tablename))
                                   for stmt in expr]
            else:
                raise BadIngredient('expression must be a string or list')
            d[k] = ingredient_from_dict(v)

        shelf = cls(d)
        shelf.Meta.table = tablename
        return shelf

    def find(self, obj, filter_to_class=Ingredient, constructor=None):
        """
        Find an Ingredient, optionally using the shelf.

        :param obj: A string or Ingredient
        :param filter_to_class: The Ingredient subclass that obj must be an
         instance of
        :param constructor: An optional callable for building Ingredients
         from obj
        :return: An Ingredient of subclass `filter_to_class`
        """
        if callable(constructor):
            obj = constructor(obj, shelf=self)

        if isinstance(obj, basestring):
            set_descending = obj.startswith('-')
            if set_descending:
                obj = obj[1:]

            if obj not in self:
                raise BadRecipe(
                    "{} doesn't exist on the shelf".format(obj))

            ingredient = self[obj]
            if not isinstance(ingredient, filter_to_class):
                raise BadRecipe('{} is not a {}'.format(
                    obj, filter_to_class))

            if set_descending:
                ingredient.ordering = 'desc'

            return ingredient
        elif isinstance(obj, filter_to_class):
            return obj
        else:
            raise BadRecipe('{} is not a {}'.format(obj,
                                                    type(filter_to_class)))

    def brew_query_parts(self):
        """ Make columns, group_bys, filters, havings
        """
        columns, group_bys, filters, havings = [], [], set(), set()
        for ingredient in self.ingredients():
            if ingredient.query_columns:
                columns.extend(ingredient.query_columns)
            if ingredient.group_by:
                group_bys.extend(ingredient.group_by)
            if ingredient.filters:
                filters.update(ingredient.filters)
            if ingredient.havings:
                havings.update(ingredient.havings)

        return {
            'columns': columns,
            'group_bys': group_bys,
            'filters': filters,
            'havings': havings,
        }

    def enchant(self, list, cache_context=None):
        """ Add any calculated values to each row of a resultset generating a
        new namedtuple

        :param list: a list of row results
        :param cache_context: optional extra context for caching
        :return: a list with ingredient.cauldron_extras added for all
                 ingredients
        """
        enchantedlist = []
        if list:
            sample_item = list[0]

            # Extra fields to add to each row
            # With extra callables
            extra_fields, extra_callables = [], []

            for ingredient in self.values():
                if not isinstance(ingredient, (Dimension, Metric)):
                    continue
                if cache_context:
                    ingredient.cache_context += str(cache_context)
                for extra_field, extra_callable in ingredient.cauldron_extras:
                    extra_fields.append(extra_field)
                    extra_callables.append(extra_callable)

            # Mixin the extra fields
            keyed_tuple = lightweight_named_tuple(
                'result', sample_item._fields + tuple(extra_fields))

            # Iterate over the results and build a new namedtuple for each row
            for row in list:
                values = row + tuple(fn(row) for fn in extra_callables)
                enchantedlist.append(keyed_tuple(values))

        return enchantedlist


class AutomaticShelf(Shelf):
    def __init__(self, table, *args, **kwargs):
        d = self._introspect(table)
        super(AutomaticShelf, self).__init__(d)

    def _introspect(self, table):
        """ Build initial shelf using table """
        d = {}
        for c in table.__table__.columns:
            if isinstance(c.type, String):
                d[c.name] = Dimension(c)
            if isinstance(c.type, (Integer, Float)):
                d[c.name] = Metric(func.sum(c))
        return d
