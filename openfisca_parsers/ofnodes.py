# -*- coding: utf-8 -*-


# OpenFisca -- A versatile microsimulation software
# By: OpenFisca Team <contact@openfisca.fr>
#
# Copyright (C) 2011, 2012, 2013, 2014, 2015, 2016 OpenFisca Team
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


"""Functions to navigate in OpenFisca AST nodes."""


from toolz.curried import filter, merge, valfilter

from . import shortid


def find_parameter_by_path_fragments(ofnodes, path_fragments):
    """
    Return the ofnode corresponding to a Parameter ofnode of given path_fragments or None if not found.
    Raises if more than 1 result.
    """
    matching_ofnodes = list(filter(
        lambda ofnode: ofnode['type'] == 'Parameter' and ofnode['path'] == path_fragments,
        ofnodes,
        ))
    assert len(matching_ofnodes) <= 1, (path_fragments, matching_ofnodes)
    return matching_ofnodes or None


def find_variable_by_name(ofnodes, name):
    """
    Return the ofnode corresponding to a Variable ofnode of given name or None if not found.
    Raises if more than 1 result.
    """
    matching_ofnodes = list(filter(
        lambda ofnode: ofnode['type'] == 'Variable' and ofnode['name'] == name,
        ofnodes,
        ))
    assert len(matching_ofnodes) <= 1, (name, matching_ofnodes)
    return matching_ofnodes[0] if matching_ofnodes else None


def make_ofnode(ofnode, rbnode, context, with_rbnodes=False):
    """Create and return a new ofnode. The ofnode is also added to the list of nodes in the context."""
    id = shortid.generate()
    ofnode = merge(ofnode, {'id': id})
    if with_rbnodes:
        ofnode = merge(ofnode, {'_rbnode': rbnode})
    context['ofnodes'].append(ofnode)
    return valfilter(lambda value: value is not None, ofnode)
