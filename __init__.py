# -*- coding: utf-8 -*-
from trytond.pool import Pool

from production import Production, Configuration


def register():
    Pool.register(
        Production,
        Configuration,
        module='production_disassembly', type_='model'
    )
