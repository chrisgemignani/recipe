# -*- coding: utf-8 -*-
"""
Recipe
~~~~~~~~~~~~~~~~~~~~~
"""
import logging

from recipe.core import Recipe
from recipe.exceptions import BadIngredient, BadRecipe
from recipe.extensions import (
    Anonymize,
    AutomaticFilters,
    BlendRecipe,
    CompareRecipe,
    RecipeExtension,
    SummarizeOver,
    Paginate,
)
from recipe.ingredients import (
    Dimension,
    DivideMetric,
    Filter,
    Having,
    IdValueDimension,
    Ingredient,
    LookupDimension,
    Metric,
    WtdAvgMetric,
)
from recipe.oven import get_oven
from recipe.shelf import AutomaticShelf, Shelf
from recipe.utils import FakerAnonymizer


class DefaultSettings(object):
    def __init__(self, *args, **kwargs):
        self.POOL_SIZE = 5
        self.POOL_RECYCLE = 60 * 60


SETTINGS = DefaultSettings()


try:  # Python 2.7+
    from logging import NullHandler
except ImportError:

    class NullHandler(logging.Handler):
        def emit(self, record):
            pass


logging.getLogger(__name__).addHandler(NullHandler())

__version__ = "0.13.1"

__all__ = [
    "BadIngredient",
    "BadRecipe",
    "Ingredient",
    "Dimension",
    "LookupDimension",
    "IdValueDimension",
    "Metric",
    "DivideMetric",
    "WtdAvgMetric",
    "Filter",
    "Having",
    "Recipe",
    "Shelf",
    "AutomaticShelf",
    "SETTINGS",
    "get_oven",
    "Anonymize",
    "AutomaticFilters",
    "BlendRecipe",
    "CompareRecipe",
    "RecipeExtension",
    "Paginate",
    "SummarizeOver",
    "FakerAnonymizer",
]
