#! /usr/bin/env python
# -*- coding: utf-8 -*-


# OpenFisca -- A versatile microsimulation software
# By: OpenFisca Team <contact@openfisca.fr>
#
# Copyright (C) 2011, 2012, 2013, 2014 OpenFisca Team
# https://github.com/openfisca
#
# This file is part of OpenFisca.
#
# OpenFisca is free software; you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# OpenFisca is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


"""Convert Python formulas to Julia using lib2to3."""


import argparse
import codecs
import collections
import datetime
import importlib
import lib2to3.pgen2.driver  # , tokenize, token
import lib2to3.pygram
import lib2to3.pytree
import logging
import os
import sys
import textwrap
import traceback

import numpy as np
from openfisca_core import formulas

from openfisca_parsers import formulas_parsers_2to3


app_name = os.path.splitext(os.path.basename(__file__))[0]
julia_file_header = textwrap.dedent(u"""\
    # OpenFisca -- A versatile microsimulation software
    # By: OpenFisca Team <contact@openfisca.fr>
    #
    # Copyright (C) 2011, 2012, 2013, 2014 OpenFisca Team
    # https://github.com/openfisca
    #
    # This file is part of OpenFisca.
    #
    # OpenFisca is free software; you can redistribute it and/or modify
    # it under the terms of the GNU Affero General Public License as
    # published by the Free Software Foundation, either version 3 of the
    # License, or (at your option) any later version.
    #
    # OpenFisca is distributed in the hope that it will be useful,
    # but WITHOUT ANY WARRANTY; without even the implied warranty of
    # MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    # GNU Affero General Public License for more details.
    #
    # You should have received a copy of the GNU Affero General Public License
    # along with this program.  If not, see <http://www.gnu.org/licenses/>.
    """)
log = logging.getLogger(app_name)


class Assignment(formulas_parsers_2to3.Assignment):
    def juliaize(self):
        parser = self.parser
        # Convert variables to Julia only once, during assignment.
        variables = [
            variable.__class__(
                container = variable.container,
                guess = variable._guess,
                name = variable.name,
                parser = parser,
                value = variable.value.juliaize() if variable.value is not None else None,
                )
            for variable in self.variables
            ]
        if len(variables) == 1:
            variable = variables[0]
            if isinstance(variable.value, parser.Call):
                call = variable.value
                call_subject = call.subject
                if isinstance(call_subject, parser.Attribute):
                    method_name = call_subject.name
                    if method_name == 'calculate':
                        method_subject = call_subject.subject
                        if isinstance(method_subject, parser.Variable) and method_subject.name == 'simulation':
                            assert len(call.positional_arguments) >= 1, call.positional_arguments
                            assert len(call.named_arguments) == 0, call.named_arguments
                            requested_variable_string = call.positional_arguments[0]
                            if isinstance(requested_variable_string, parser.String):
                                assert requested_variable_string.value == variable.name, str((variable.name,
                                    requested_variable_string.value))
                                return parser.Call(
                                    container = self.container,
                                    # guess = parser.ArrayHandle(parser = parser),  TODO
                                    parser = parser,
                                    positional_arguments = [Variable(
                                        container = self.container,
                                        # guess = parser.ArrayHandle(parser = parser),  TODO
                                        name = variable.name,
                                        parser = parser,
                                        )] + call.positional_arguments[1:],
                                    subject = parser.Function(  # TODO: Use Macro or MacroCall.
                                        name = u'@calculate',
                                        parser = parser,
                                        ),
                                    )
        return self.__class__(
            container = self.container,
            guess = self._guess,
            operator = self.operator,
            parser = self.parser,
            variables = variables,
            )

    def source_julia(self):
        left_str = u', '.join(
            variable.name
            for variable in self.variables
            )
        right_str = u', '.join(
            variable.value.source_julia()
            if variable.value is not None
            else 'TODO'
            for variable in self.variables
            )
        return u'{} {} {}'.format(left_str, self.operator, right_str)


class Attribute(formulas_parsers_2to3.Attribute):
    def juliaize(self):
        return self.__class__(
            container = self.container,
            guess = self._guess,
            name = self.name,
            parser = self.parser,
            subject = self.subject.juliaize(),
            )

    def source_julia(self):
        return u"{}.{}".format(
            self.subject.source_julia(),
            self.name,
            )


class Call(formulas_parsers_2to3.Call):
    def juliaize(self):
        parser = self.parser
        named_arguments = collections.OrderedDict(
            (argument_name, argument_value.juliaize())
            for argument_name, argument_value in self.named_arguments.iteritems()
            )
        positional_arguments = [
            argument_value.juliaize()
            for argument_value in self.positional_arguments
            ]
        subject = self.subject.juliaize()
        if isinstance(subject, parser.Attribute):
            method_name = subject.name
            if method_name == 'offset':
                method_subject = subject.subject.juliaize()
                method_subject_guess = method_subject.guess
                if isinstance(method_subject_guess, parser.Instant):
                    assert len(self.positional_arguments) == 2, self.positional_arguments
                    delta, unit = self.positional_arguments
                    if isinstance(delta, parser.String) and delta.value == 'first-of':
                        if isinstance(unit, parser.String) and unit.value == 'month':
                            return parser.Call(
                                container = self.container,
                                guess = parser.Instant(parser = parser),
                                parser = parser,
                                positional_arguments = [method_subject],
                                subject = parser.Function(
                                    name = u'firstdayofmonth',
                                    parser = parser,
                                    ),
                                )
                        if isinstance(unit, parser.String) and unit.value == 'year':
                            return parser.Call(
                                container = self.container,
                                guess = parser.Instant(parser = parser),
                                parser = parser,
                                positional_arguments = [method_subject],
                                subject = parser.Function(
                                    name = u'firstdayofyear',
                                    parser = parser,
                                    ),
                                )
            if method_name == 'period':
                method_subject = subject.subject.juliaize()
                method_subject_guess = method_subject.guess
                if isinstance(method_subject_guess, parser.Instant):
                    assert len(self.positional_arguments) >= 1, self.positional_arguments
                    unit = self.positional_arguments[0]
                    if isinstance(unit, parser.String) and unit.value == 'month':
                        return parser.Call(
                            container = self.container,
                            guess = parser.Period(parser = parser),
                            parser = parser,
                            positional_arguments = [method_subject] + self.positional_arguments[1:],
                            subject = parser.Function(
                                name = u'MonthPeriod',
                                parser = parser,
                                ),
                            )
                    if isinstance(unit, parser.String) and unit.value == 'year':
                        return parser.Call(
                            container = self.container,
                            guess = parser.Period(parser = parser),
                            parser = parser,
                            positional_arguments = [method_subject] + self.positional_arguments[1:],
                            subject = parser.Function(
                                name = u'YearPeriod',
                                parser = parser,
                                ),
                            )
        elif isinstance(subject, parser.Function):
            function_name = subject.name
            if function_name == 'date':
                assert len(self.positional_arguments) == 3, self.positional_arguments
                return parser.Call(
                    container = self.container,
                    guess = parser.Date(parser = parser),
                    parser = parser,
                    positional_arguments = self.positional_arguments,
                    subject = parser.Function(
                        name = u'Date',
                        parser = parser,
                        ),
                    )
        return self.__class__(
            container = self.container,
            guess = self._guess,
            named_arguments = named_arguments,
            parser = self.parser,
            positional_arguments = positional_arguments,
            subject = subject,
            )

    def source_julia(self):
        arguments_str = [
            argument_value.source_julia()
            for argument_value in self.positional_arguments
            ] + [
            u'{} = {}'.format(argument_name, argument_value.source_julia())
            for argument_name, argument_value in self.named_arguments.iteritems()
            ]
        return u"{}({})".format(
            self.subject.source_julia(),
            u', '.join(arguments_str),
            )


class FormulaClass(formulas_parsers_2to3.FormulaClass):
    def juliaize(self):
        return self

    def source_julia(self):
        parser = self.parser
        statements = None
        for formula in self.variable_by_name.itervalues():
            if isinstance(formula, parser.FormulaFunction):
                statements = formula.juliaize().source_julia_statements()
                break
        return textwrap.dedent(u"""
            {call} do simulation, variable, period
            {statements}end
            """).format(
            call = parser.source_julia_column_without_function(),
            statements = statements or u'',
            )


class FormulaFunction(formulas_parsers_2to3.FormulaFunction):
    def juliaize(self):
        return self

    def source_julia_statements(self):
        return u''.join(
            u'  {}\n'.format(statement.juliaize().source_julia())
            for statement in self.body
            )


class Function(formulas_parsers_2to3.Variable):
    def juliaize(self):
        return self  # Conversion of function to Julia is done only once, during declaration.

    def source_julia(self):
        return self.name


class Instant(formulas_parsers_2to3.Instant):
    def juliaize(self):
        return self

    # def juliaize_attribute(self, attribute):
    #     if attribute.name == 'offset':
    #         return parser.Instant(wrapper = attribute, parser = parser)
    #     assert False, "Unknown attribute for instant: {}".format(attribute.name)


class Period(formulas_parsers_2to3.Period):
    def juliaize(self):
        return self

    # def juliaize_attribute(self, attribute):
    #     if attribute.name == 'start':
    #         return parser.Instant(wrapper = attribute, parser = parser)
    #     assert False, "Unknown attribute for period: {}".format(attribute.name)


class Return(formulas_parsers_2to3.Return):
    def juliaize(self):
        return self.__class__(
            container = self.container,
            guess = self._guess,
            parser = self.parser,
            value = self.value.juliaize(),
            )

    def source_julia(self):
        if isinstance(self.value, self.parser.Tuple):
            return u'return {}'.format(u', '.join(
                item.source_julia()
                for item in self.value.value
                ))
        return u"return {}".format(self.value.source_julia())


class Simulation(formulas_parsers_2to3.Simulation):
    def juliaize(self):
        return self


class String(formulas_parsers_2to3.String):
    def juliaize(self):
        return self

    def source_julia(self):
        return generate_string_julia_source(self.value)


class Tuple(formulas_parsers_2to3.Tuple):
    def juliaize(self):
        return self.__class__(
            container = self.container,
            guess = self._guess,
            parser = self.parser,
            value = tuple(
                item.juliaize()
                for item in self.value),
            )

    def source_julia(self):
        return u'({})'.format(u', '.join(
            item.source_julia()
            for item in self.value
            ))


class Variable(formulas_parsers_2to3.Variable):
    def juliaize(self):
        return self  # Conversion of variable to Julia is done only once, during assignment.

    # def juliaize_attribute(self, attribute):
    #     if self.value is not None:
    #         value = self.value.copy()
    #         value.wrapper = self
    #         return value.juliaize_attribute(attribute, parser = self.parser)
    #     return attribute

    def source_julia(self):
        return self.name


# Julia parser & compiler


class Parser(formulas_parsers_2to3.Parser):
    Assignment = Assignment
    Attribute = Attribute
    Call = Call
    FormulaClass = FormulaClass
    FormulaFunction = FormulaFunction
    Function = Function
    Instant = Instant
    Period = Period
    Return = Return
    Simulation = Simulation
    String = String
    Tuple = Tuple
    Variable = Variable

    def source_julia_column_without_function(self):
        column = self.column
        tax_benefit_system = self.tax_benefit_system

        column_attributes_name = set(column.__dict__.keys())
        unexpected_attributes_name = column_attributes_name.difference((
            'cerfa_field',
            'default',
            'dtype',
            'end',
            'entity',
            'entity_key_plural',
            'enum',
            'formula_class',
            'is_permanent',
            'label',
            'max_length',
            'name',
            'start',
            'url',
            'val_type',
            ))
        assert not unexpected_attributes_name, "Unexpected attributes in column {}: {}".format(column.name,
            ", ".join(sorted(unexpected_attributes_name)))

        cell_type = {
            bool: 'Bool',
            float: 'Float32',
            np.float32: 'Float32',
            np.int16: 'Int16',
            np.int32: 'Int32',
            object: 'UTF8String',
            'datetime64[D]': 'Date',
            '|S5': 'UTF8String',  # TODO
            }.get(column.dtype)
        assert cell_type is not None, "Unexpected dtype in column {}: {}".format(column.name, column.dtype)

        cerfa_field = column.cerfa_field
        if isinstance(cerfa_field, basestring):
            cerfa_field_str = u'"{}"'.format(cerfa_field)
        elif isinstance(cerfa_field, dict):
            cerfa_field_str = u'[{}]'.format(u', '.join(
                u'{} => "{}"'.format(role, field)
                for role, field in sorted(cerfa_field.iteritems())
                ))
        else:
            assert cerfa_field is None
            cerfa_field_str = None

        default = column.__dict__.get('default')
        if default is None:
            default_str = None
        elif default is True:
            default_str = "true"
        elif isinstance(default, datetime.date):
            default_str = u"Date({}, {}, {})".format(default.year, default.month, default.day)
        elif isinstance(default, (float, int)):
            default_str = str(default)
        elif default == '':
            default_str = '""'
        else:
            assert default is None, "Unexpected default value: {} (type: {})".format(default, type(default))

        enum = column.__dict__.get('enum')
        if enum is None:
            values_str = None
        else:
            values_str = u"[\n{}  ]".format(u''.join(
                u'    {} => "{}",\n'.format(index, symbol)
                for index, symbol in sorted(
                    (index1, symbol1)
                    for symbol1, index1 in enum
                    )
                ))

        # max_length = column.__dict__.get('max_length')  TODO?

        start_date = column.start
        stop_date = column.end

        named_arguments = u''.join(
            u'  {},\n'.format(named_argument)
            for named_argument in [
                u'cell_default = {}'.format(default_str) if default_str is not None else None,
                u'cell_format = "{}"'.format(column.val_type) if column.val_type is not None else None,
                u'cerfa_field = {}'.format(cerfa_field_str) if cerfa_field_str is not None else None,
                (u"label = {}".format(generate_string_julia_source(column.label))
                    if column.label not in (u'', column.name) else None),
                # u'max_length = {}'.format(max_length) if max_length is not None else None,  TODO?
                "permanent = true" if column.is_permanent else None,
                u"start_date = Date({}, {}, {})".format(start_date.year, start_date.month,
                    start_date.day) if start_date is not None else None,
                u"stop_date = Date({}, {}, {})".format(stop_date.year, stop_date.month,
                    stop_date.day) if stop_date is not None else None,
                (u"url = {}".format(generate_string_julia_source(column.url))
                    if column.url is not None
                    else None),
                u"values = {}".format(values_str) if values_str is not None else None,
                ]
            if named_argument is not None
            )
        if named_arguments:
            named_arguments = u',\n{}'.format(named_arguments)
        return u"""@define_variable({name}, {entity}_definition, {cell_type}{named_arguments})""".format(
            cell_type = cell_type,
            entity = tax_benefit_system.entity_class_by_key_plural[column.entity_key_plural].key_singular,
            name = column.name,
            named_arguments = named_arguments,
            )


def generate_date_range_value_julia_source(date_range_value_json):
    for key in date_range_value_json.iterkeys():
        assert key in (
            'comment',
            'start',
            'stop',
            'value',
            ), "Unexpected item key for date range value: {}".format(key)
    comment = date_range_value_json.get('comment')
    return u'DateRangeValue({start_date}, {stop_date}, {value}{comment})'.format(
        comment = u', comment = {}'.format(generate_string_julia_source(comment)) if comment else u'',
        start_date = u'Date({}, {}, {})'.format(*date_range_value_json['start'].split(u'-')),
        stop_date = u'Date({}, {}, {})'.format(*date_range_value_json['stop'].split(u'-')),
        value = unicode(date_range_value_json['value']).lower(),  # Method lower() is used for True and False.
        )


def generate_legislation_node_julia_source(node_json, check_start_date_julia_source = None,
        check_stop_date_julia_source = None, comments = None, descriptions = None, julia_source_by_path = None,
        path_fragments = None):
    if node_json['@type'] == 'Node':
        for key in node_json.iterkeys():
            assert key in (
                '@context',
                '@type',
                'children',
                'comment',
                'description',
                'start',
                'stop',
                ), "Unexpected item key for node: {}".format(key)
        for child_code, child_json in node_json['children'].iteritems():
            generate_legislation_node_julia_source(
                child_json,
                check_start_date_julia_source = check_start_date_julia_source,
                check_stop_date_julia_source = check_stop_date_julia_source,
                comments = comments + [node_json.get('comment')],
                descriptions = descriptions + [node_json.get('description')],
                julia_source_by_path = julia_source_by_path,
                path_fragments = path_fragments + [child_code],
                )
    elif node_json['@type'] == 'Parameter':
        for key in node_json.iterkeys():
            assert key in (
                '@type',
                'comment',
                'description',
                'format',
                'unit',
                'values',
                ), "Unexpected item key for parameter: {}".format(key)

        format = node_json.get('format')
        type_str = {
            None: u'Float32',
            'boolean': u'Bool',
            'float': u'Float32',
            'integer': u'Int32',
            'rate': u'Float32',
            }[format]

        named_arguments = collections.OrderedDict()

        unit = node_json.get('unit')
        if unit is not None:
            named_arguments['unit'] = u'"{}"'.format(unit)

        named_arguments['check_start_date'] = check_start_date_julia_source
        named_arguments['check_stop_date'] = check_stop_date_julia_source

        description = u' ; '.join(
            fragment
            for fragment in descriptions + [node_json.get('description')]
            if fragment
            )
        if description:
            named_arguments['description'] = generate_string_julia_source(description)

        comment = u' ; '.join(
            fragment
            for fragment in comments + [node_json.get('comment')]
            if fragment
            )
        if comment:
            named_arguments['comment'] = generate_string_julia_source(comment)

        julia_source_by_path[u'.'.join(path_fragments)] = textwrap.dedent(u"""
            {name} = Parameter{{{type}}}(
              [
            {values}  ],
            {named_arguments})
            """).format(
            name = u'_'.join(path_fragments),
            named_arguments = u''.join(
                u'  {} = {},\n'.format(argument_name, argument_str)
                for argument_name, argument_str in named_arguments.iteritems()
                ),
            type = type_str,
            values = u''.join(
                u'    {},\n'.format(generate_date_range_value_julia_source(date_range_value_json))
                for date_range_value_json in reversed(node_json['values'])
                ),
            )
    elif node_json['@type'] == 'Scale':
        for key in node_json.iterkeys():
            assert key in (
                '@type',
                'brackets',
                'comment',
                'description',
                'option',
                'unit',
                ), "Unexpected item key for tax scale: {}".format(key)

        tax_scale_type = None
        brackets_julia_source = []
        for bracket_json in node_json['brackets']:
            for bracket_key in bracket_json.iterkeys():
                assert bracket_key in (
                    'amount',
                    'base',
                    'rate',
                    'threshold',
                    ), "Unexpected item key for bracket: {}".format(bracket_key)

            amount_json = bracket_json.get('amount')
            if amount_json is None:
                amount_julia_source = u''
            else:
                if tax_scale_type is None:
                    tax_scale_type = u'AmountTaxScale'
                else:
                    assert tax_scale_type == u'AmountTaxScale'
                date_range_values_julia_source = u'\n'.join(
                    u'        {},\n'.format(generate_date_range_value_julia_source(date_range_value_json))
                    for date_range_value_json in amount_json
                    )
                amount_julia_source = u'      amount = [\n{}      ],\n'.format(date_range_values_julia_source)

            base_json = bracket_json.get('base')
            if base_json is None:
                base_julia_source = u''
            else:
                date_range_values_julia_source = u'\n'.join(
                    u'        {},\n'.format(generate_date_range_value_julia_source(date_range_value_json))
                    for date_range_value_json in base_json
                    )
                base_julia_source = u'      base = [\n{}      ],\n'.format(date_range_values_julia_source)

            rate_json = bracket_json.get('rate')
            if rate_json is None:
                rate_julia_source = u''
            else:
                if tax_scale_type is None:
                    tax_scale_type = u'RateTaxScale'
                else:
                    assert tax_scale_type == u'RateTaxScale'
                date_range_values_julia_source = u'\n'.join(
                    u'        {},\n'.format(generate_date_range_value_julia_source(date_range_value_json))
                    for date_range_value_json in rate_json
                    )
                rate_julia_source = u'      rate = [\n{}      ],\n'.format(date_range_values_julia_source)

            threshold_json = bracket_json.get('threshold')
            if threshold_json is None:
                threshold_julia_source = u''
            else:
                date_range_values_julia_source = u'\n'.join(
                    u'        {},\n'.format(generate_date_range_value_julia_source(date_range_value_json))
                    for date_range_value_json in threshold_json
                    )
                threshold_julia_source = u'      threshold = [\n{}      ],\n'.format(date_range_values_julia_source)

            if tax_scale_type == 'AmountTaxScale':
                bracket_julia_source = u'    AmountBracket(\n{threshold}{amount}{base}    ),\n'.format(
                    amount = amount_julia_source,
                    base = base_julia_source,
                    threshold = threshold_julia_source,
                    )
            else:
                bracket_julia_source = u'    RateBracket(\n{threshold}{rate}{base}    ),\n'.format(
                    base = base_julia_source,
                    rate = rate_julia_source,
                    threshold = threshold_julia_source,
                    )
            brackets_julia_source.append(bracket_julia_source)

        option = node_json.get('option')
        assert option in (
            None,
            'contrib',
            'main-d-oeuvre',
            'noncontrib',
            ), "Unexpected option for tax scale: {}".format(option)
        # TODO

        named_arguments = collections.OrderedDict()

        unit = node_json.get('unit')
        if unit is not None:
            named_arguments['unit'] = u'"{}"'.format(unit)

        named_arguments['check_start_date'] = check_start_date_julia_source
        named_arguments['check_stop_date'] = check_stop_date_julia_source

        description = u' ; '.join(
            fragment
            for fragment in descriptions + [node_json.get('description')]
            if fragment
            )
        if description:
            named_arguments['description'] = generate_string_julia_source(description)

        comment = u' ; '.join(
            fragment
            for fragment in comments + [node_json.get('comment')]
            if fragment
            )
        if comment:
            named_arguments['comment'] = generate_string_julia_source(comment)

        julia_source_by_path[u'.'.join(path_fragments)] = textwrap.dedent(u"""
            {name} = {tax_scale_type}(
              [
            {brackets}  ],
            {named_arguments})
            """).format(
            brackets = u''.join(brackets_julia_source),
            name = u'_'.join(path_fragments),
            named_arguments = u''.join(
                u'  {} = {},\n'.format(argument_name, argument_str)
                for argument_name, argument_str in named_arguments.iteritems()
                ),
            tax_scale_type = tax_scale_type,
            )
    else:
        assert False, "Unexpected type for node: {}".format(node_json['@type'])


def generate_string_julia_source(s):
    if u'\n' in s:
        return u'"""{}"""'.format(s.replace(u'"', u'\\"'))
    return u'"{}"'.format(s.replace(u'"', u'\\"'))


def main():
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument('julia_package_dir', help = u'path of the directory of the OpenFisca Julia package')
    parser.add_argument('-c', '--country-package', default = 'openfisca_france',
        help = u'name of the OpenFisca package to use for country-specific variables & formulas')
    parser.add_argument('-v', '--verbose', action = 'store_true', default = False, help = "increase output verbosity")
    args = parser.parse_args()
    logging.basicConfig(level = logging.DEBUG if args.verbose else logging.WARNING, stream = sys.stdout)

    country_package = importlib.import_module(args.country_package)
    TaxBenefitSystem = country_package.init_country()
    tax_benefit_system = TaxBenefitSystem()

    parser = Parser(
        driver = lib2to3.pgen2.driver.Driver(lib2to3.pygram.python_grammar, convert = lib2to3.pytree.convert,
            logger = log),
        tax_benefit_system = tax_benefit_system,
        )

    legislation_json = tax_benefit_system.legislation_json
    parameter_julia_source_by_path = collections.OrderedDict()
    generate_legislation_node_julia_source(
        legislation_json,
        check_start_date_julia_source = u'Date({}, {}, {})'.format(*legislation_json['start'].split(u'-')),
        check_stop_date_julia_source = u'Date({}, {}, {})'.format(*legislation_json['stop'].split(u'-')),
        comments = [],
        descriptions = [],
        julia_source_by_path = parameter_julia_source_by_path,
        path_fragments = [],
        )
    julia_path = os.path.join(args.julia_package_dir, 'src', 'parameters.jl')
    with codecs.open(julia_path, 'w', encoding = 'utf-8') as julia_file:
        julia_file.write(julia_file_header)
        julia_file.write(u'\n')
        for parameter_julia_source in parameter_julia_source_by_path.itervalues():
            julia_file.write(parameter_julia_source)

    input_variable_definition_julia_str_by_name = collections.OrderedDict()
    output_variable_definition_julia_str_by_name_by_module_name = {}
    for column in tax_benefit_system.column_by_name.itervalues():
        print column.name
        parser.column = column

        column_formula_class = column.formula_class
        if column_formula_class is None:
            # Input variable
            input_variable_definition_julia_str_by_name[column.name] = parser.source_julia_column_without_function()
            continue
        if issubclass(column_formula_class, formulas.AbstractEntityToEntity):
            # EntityToPerson or PersonToEntity converters
            continue

        try:
            formula_class_wrapper = parser.FormulaClassFileInput.parse(column_formula_class, parser = parser)
        except:
            # Stop conversion of columns, but write the existing results to Julia files.
            traceback.print_exc()
            break
        # if issubclass(column_formula_class, formulas.DatedFormula):
        #     function_functions = []
        #     for name, value in formula_class_wrapper.value_by_name.iteritems():
        #         if isinstance(value, parser.Decorator) and value.name == u'dated_function':
        #             function_function = value.decorated
        #             assert isinstance(function_function, parser.Function)
        #             assert name.startswith('function_') or name == 'function', name
        #             function_functions.append(function_function)
        # else:
        #     assert issubclass(column_formula_class, formulas.SimpleFormula), column_formula_class
        #     function_functions = [formula_class_wrapper.value_by_name['function']]
        julia_str = formula_class_wrapper.juliaize().source_julia()
        module_name = formula_class_wrapper.containing_module.python.__name__
        assert module_name.startswith('openfisca_france.model.')
        module_name = module_name[len('openfisca_france.model.'):]
        output_variable_definition_julia_str_by_name_by_module_name.setdefault(module_name, {})[column.name] = julia_str

    julia_path = os.path.join(args.julia_package_dir, 'src', 'input_variables.jl')
    with codecs.open(julia_path, 'w', encoding = 'utf-8') as julia_file:
        julia_file.write(julia_file_header)
        julia_file.write(u'\n')
        for input_variable_definition_julia_str in input_variable_definition_julia_str_by_name.itervalues():
            julia_file.write(u'\n')
            julia_file.write(input_variable_definition_julia_str)
            julia_file.write(u'\n')

    for module_name, julia_str_by_name in output_variable_definition_julia_str_by_name_by_module_name.iteritems():
        julia_relative_path = os.path.join(*module_name.split('.')) + '.jl'
        julia_path = os.path.join(args.julia_package_dir, 'src', julia_relative_path)
        julia_dir = os.path.dirname(julia_path)
        if not os.path.exists(julia_dir):
            os.makedirs(julia_dir)
        with codecs.open(julia_path, 'w', encoding = 'utf-8') as julia_file:
            julia_file.write(julia_file_header)
            for column_name, julia_str in sorted(julia_str_by_name.iteritems()):
                julia_file.write(u'\n')
                julia_file.write(julia_str)
                julia_file.write(u'\n')

    return 0


if __name__ == "__main__":
    sys.exit(main())
