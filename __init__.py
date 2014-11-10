# -*- coding: utf-8 -*-
"""
    __init__.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool

from production import Production, Configuration


def register():
    Pool.register(
        Production,
        Configuration,
        module='production_disassembly', type_='model'
    )
