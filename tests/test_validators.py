# -*- coding: utf-8 -*-
from cerberus import Validator
from cerberus.tests import assert_normalized, assert_success
from sqlalchemy import func
from tests.test_base import MyTable

from recipe.utils import AttrDict, disaggregate, replace_whitespace_with_space
from recipe.validators import (
    IngredientValidator, aggregated_field_schema, condition_schema,
    default_field_schema
)


class TestValidateIngredient(object):

    def setup(self):
        self.validator = IngredientValidator()
        self.field_validator = Validator(
            schema=default_field_schema, allow_unknown=False
        )

    def test_good(self):
        testers = [
            {
                'kind': 'Metric',
                'field': 'moo',
                'format': 'comma'
            },
            {
                'kind': 'Metric',
                'format': 'comma',
                'icon': 'foo',
                'field': {
                    'value': 'cow',
                    'condition': {
                        'field': 'moo2',
                        'in': 'wo',
                        # 'gt': 2
                    }
                }
            }
        ]
        for d in testers:
            assert self.validator.validate(d)

    def test_ingredient_kind(self):
        # Dicts to validate and the results
        good_values = [({
            'field': 'moo'
        }, {
            'kind': 'Metric',
            'field': {
                'value': 'moo',
                'aggregation': None
            }
        }), ({
            'kind': 'Ingredient',
            'field': 'moo',
        }, {
            'kind': 'Ingredient',
            'field': {
                'value': 'moo',
                'aggregation': None
            }
        })]

        for d, result in good_values:
            assert_success(d, validator=self.validator)
            # assert self.validator.validate(d)
            # self.validator.normalized(d) == result

        # Dicts that fail to validate and the errors
        bad_values = [
            ({
                'kind': 'asa',
                'field': 'moo'
            }, "{'kind': ['unallowed value asa']}"),
            ({
                'kind': 'Sque',
                'field': 'moo'
            }, "{'kind': ['unallowed value Sque']}"),
        ]
        for d, result in bad_values:
            assert self.validator.validate(d) == False
            assert str(self.validator.errors) == result

    def test_ingredient_format(self):
        # Dicts to validate and the results
        good_values = [
            ({
                'format': 'comma',
                'field': 'moo',
            }, {
                'kind': 'Metric',
                'format': ',.0f',
                'field': {
                    'value': 'moo',
                    'aggregation': None
                }
            }),
            ({
                'format': ',.0f',
                'field': 'moo'
            }, {
                'kind': 'Metric',
                'format': ',.0f',
                'field': {
                    'value': 'moo',
                    'aggregation': None
                }
            }),
            ({
                'format': 'cow',
                'field': 'moo'
            }, {
                'kind': 'Metric',
                'field': {
                    'value': 'moo',
                    'aggregation': None
                },
                'format': 'cow'
            }),
            # FIXME: Why is this not 'field': {'value': 'grass'}
            ({
                'format': 'cow',
                'field': 'grass'
            }, {
                'kind': 'Metric',
                'format': 'cow',
                'field': {
                    'value': 'grass',
                    'aggregation': None
                }
            }),
        ]
        for document, expected in good_values:
            assert self.validator.validate(document)
            assert self.validator.document == expected

        # We can add new format_lookups
        IngredientValidator.format_lookup['cow'] = '.0f "moos"'
        good_values = [
            ({
                'format': 'cow',
                'field': 'grass',
            }, {
                'kind': 'Metric',
                'field': {
                    'value': 'grass',
                    'aggregation': None
                },
                'format': '.0f "moos"'
            }),
        ]
        for document, expected in good_values:
            assert self.validator.validate(document)
            self.validator.document == expected

        # Dicts that fail to validate and the errors
        bad_values = [
            ({
                'format': 2,
                'field': 'moo',
            }, "{'format': ['must be of string type']}"),
            ({
                'format': [],
                'field': 'moo',
            }, "{'format': ['must be of string type']}"),
            ({
                'format': ['comma'],
                'field': 'moo',
            }, "{'format': ['must be of string type']}"),
        ]
        for document, errors in bad_values:
            assert not self.validator.validate(document)
            assert str(self.validator.errors) == errors

    def test_ingredient_field(self):
        # Dicts to validate and the results
        good_values = [({
            'field': 'moo'
        }, {
            'kind': 'Metric',
            'field': {
                'value': 'moo',
                'aggregation': None
            }
        })]
        IngredientValidator.format_lookup['cow'] = '.0f "moos"'
        for document, expected in good_values:
            assert self.validator.validate(document)
            assert self.validator.document == expected

        # Dicts that fail to validate and the errors
        bad_values = [
            ({
                'field': 2
            }, "{'field': ['must be of dict type']}"),
            ({
                'field': 2.1
            }, "{'field': ['must be of dict type']}"),
            # TODO: Why don't these fail validation
            # ({'field': tuple()}, "{'field': ['must be of dict type']}"),
            # ({'field': []}, "{'field': ['must be of dict type']}"),
            # ({'field': ['comma']}, "{'field': ['must be of dict type']}"),
        ]
        for document, errors in bad_values:
            assert not self.validator.validate(document)
            assert str(self.validator.errors) == errors


class TestValidateField(object):

    def setup(self):
        self.validator = IngredientValidator(
            schema=default_field_schema, allow_unknown=False
        )

    def test_field_value(self):
        # Dicts to validate and the results
        good_values = [
            ({
                'value': 'foo'
            }, {
                'value': 'foo',
                'aggregation': None,
            }),
            ({
                'value': 'foo',
                'aggregation': 'sum'
            }, {
                'value': 'foo',
                'aggregation': 'sum'
            }),
        ]

        for document, expected in good_values:
            assert self.validator.validate(document)
            assert self.validator.document == expected

        # Dicts that fail to validate and the errors
        bad_values = [
            ({
                'kind': 'asa'
            }, "{'kind': ['unknown field'], 'value': ['required field']}"),
            ({
                'value': 'foo',
                'aggregation': 'cow'
            }, "{'aggregation': ['unallowed value cow']}"),
        ]
        for document, errors in bad_values:
            assert not self.validator.validate(document)
            assert str(self.validator.errors) == errors


class TestValidateAggregatedField(object):

    def setup(self):
        self.validator = IngredientValidator(
            schema=aggregated_field_schema, allow_unknown=False
        )

    def test_field_value(self):
        # Dicts to validate and the results
        good_values = [
            # Aggregation gets injected
            ({
                'value': 'moo'
            }, {
                'value': 'moo',
                'aggregation': 'sum'
            }),
            # None gets overridden with default_aggregation
            ({
                'value': 'qoo',
                'aggregation': None
            }, {
                'value': 'qoo',
                'aggregation': 'sum'
            }),
            ({
                'value': 'foo',
                'aggregation': 'none'
            }, {
                'value': 'foo',
                'aggregation': 'none'
            }),
            # Other aggregations are untouched
            ({
                'value': 'foo',
                'aggregation': 'sum'
            }, {
                'value': 'foo',
                'aggregation': 'sum'
            }),
            ({
                'value': 'foo',
                'aggregation': 'count'
            }, {
                'value': 'foo',
                'aggregation': 'count'
            }),
        ]

        for document, expected in good_values:
            assert self.validator.validate(document)
            assert self.validator.document == expected

        # We can change the default aggregation
        IngredientValidator.default_aggregation = 'count'
        good_values = [
            # Aggregation gets injected
            ({
                'value': 'moo'
            }, {
                'value': 'moo',
                'aggregation': 'count'
            }),
            # None gets overridden with default_aggregation
            ({
                'value': 'qoo',
                'aggregation': None
            }, {
                'value': 'qoo',
                'aggregation': 'count'
            }),
            # Other aggregations are untouched
            ({
                'value': 'foo',
                'aggregation': 'none'
            }, {
                'value': 'foo',
                'aggregation': 'none'
            }),
            ({
                'value': 'foo',
                'aggregation': 'sum'
            }, {
                'value': 'foo',
                'aggregation': 'sum'
            }),
            ({
                'value': 'foo',
                'aggregation': 'count'
            }, {
                'value': 'foo',
                'aggregation': 'count'
            }),
        ]

        for document, expected in good_values:
            assert self.validator.validate(document)
            assert self.validator.document == expected

        # Dicts that fail to validate and the errors
        bad_values = [
            ({
                'kind': 'asa'
            }, "{'kind': ['unknown field'], 'value': ['required field']}"),
            ({
                'value': 'foo',
                'aggregation': 'cow'
            }, "{'aggregation': ['unallowed value cow']}"),
            ({
                'value': 'foo',
                'aggregation': ['cow']
            }, "{'aggregation': ['must be of string type']}"),
        ]
        for document, errors in bad_values:
            assert not self.validator.validate(document)
            assert str(self.validator.errors) == errors

    def test_field_condition(self):
        # Dicts to validate and the results
        good_values = [
            # Aggregation gets injected
            ({
                'value': 'moo',
                'aggregation': 'sum',
                'condition': {
                    'field': 'cow',
                    'in': ['1', '2']
                }
            }, {
                'value': 'moo',
                'aggregation': 'sum',
                'condition': {
                    'field': {
                        'aggregation': None,
                        'value': 'cow'
                    },
                    'in': ['1', '2']
                }
            }),
        ]

        for document, expected in good_values:
            assert self.validator.validate(document)
            assert self.validator.document == expected


class TestValidateCondition(object):

    def setup(self):
        self.validator = IngredientValidator(
            schema=condition_schema, allow_unknown=False
        )

    def test_condition(self):
        # Dicts to validate and the results
        good_values = [
            ({
                'field': 'foo',
                'in': ['1', '2']
            }, {
                'field': {
                    'aggregation': None,
                    'value': 'foo'
                },
                'in': ['1', '2']
            }),
            # Scalars get turned into lists where appropriate
            ({
                'field': 'foo',
                'in': '1'
            }, {
                'field': {
                    'aggregation': None,
                    'value': 'foo'
                },
                'in': ['1']
            }),
        ]

        for document, expected in good_values:
            assert self.validator.validate(document)
            assert self.validator.document == expected

        # Dicts that fail to validate and the errors they make
        bad_values = [
            ({
                'field': 'foo',
                'kind': 'asa'
            }, "{'kind': ['unknown field']}"),
            ({}, "{'field': ['required field']}"),
        ]
        for document, errors in bad_values:
            assert not self.validator.validate(document)
            assert str(self.validator.errors) == errors
