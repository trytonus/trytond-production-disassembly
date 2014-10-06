# -*- coding: utf-8 -*-
"""
    production_disassembly.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from decimal import Decimal
from collections import namedtuple

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.modules.production import production


__metaclass__ = PoolMeta
__all__ = ['Production', 'Configuration']
BOM_CHANGES = production.BOM_CHANGES + ['disassembly']


class Configuration:
    __name__ = 'production.configuration'

    disassembly_difference_product = fields.Many2One(
        'product.product', 'Disassembly Difference Product'
    )

    @classmethod
    def get_disassembly_difference_product(cls):
        product = cls(1).disassembly_difference_product

        if product:
            return product

        cls.raise_user_error(
            "Please set disassembly difference product in production "
            "configuration"
        )


class Production:

    __name__ = 'production'

    disassembly = fields.Boolean(
        'Disassemble ?', states={
            'readonly': ~Eval('state').in_(['request', 'draft']),
            'invisible': ~Eval('product'),
        }, depends=['product']
    )

    def explode_bom(self):
        """
        Change the way explode BOM works to respect disassembly
        """
        pool = Pool()
        Configuration = pool.get('production.configuration')

        if not (self.bom and self.product and self.uom):
            return {}

        if not self.disassembly:
            return super(Production, self).explode_bom()

        inputs = {
            'remove': [r.id for r in self.inputs or []],
            'add': [],
        }
        outputs = {
            'remove': [r.id for r in self.outputs or []],
            'add': [],
        }
        changes = {
            'inputs': inputs,
            'outputs': outputs,
            'cost': Decimal(0),
        }

        if self.warehouse:
            storage_location = self.warehouse.storage_location
        else:
            storage_location = None

        factor = self.bom.compute_factor(
            self.product, self.quantity or 0, self.uom
        )

        # Disassembly inverts outputs and inputs.
        bom_inputs, bom_outputs = self.bom.outputs, self.bom.inputs

        for input_ in bom_inputs:
            quantity = input_.compute_quantity(factor)
            values = self._explode_move_values(
                storage_location, self.location, self.company, input_, quantity
            )
            if values:
                changes['cost'] += (
                    Decimal(str(quantity)) * input_.product.cost_price
                )
                inputs['add'].append((-1, values))

        cost_of_outputs = Decimal('0')
        for output in bom_outputs:
            quantity = output.compute_quantity(factor)
            values = self._explode_move_values(
                self.location, storage_location, self.company, output, quantity
            )
            if values:
                values['unit_price'] = output.product.cost_price
                cost_of_outputs += (
                    Decimal(str(quantity)) * output.product.cost_price
                )
                outputs['add'].append((-1, values))

        if not self.company.currency.is_zero(changes['cost'] - cost_of_outputs):
            # There is a cost difference because we cannot set the cost
            # price of inputs. Add a scrap product in the outputs to
            # adjust this cost difference.
            disassembly_difference_product = \
                Configuration.get_disassembly_difference_product()

            # If it walks like a duck its a duck!
            # Misuse duck typing to reuse _explode_move_values by sending
            # an object which looks like bom_io, but is just a named tuple
            # :)
            BomIODuck = namedtuple('BomIODuck', ['product', 'uom'])
            bom_io_duck = BomIODuck(
                product=disassembly_difference_product,
                uom=disassembly_difference_product.default_uom
            )

            values = self._explode_move_values(
                self.location, storage_location, self.company,
                bom_io_duck, 1
            )
            values['unit_price'] = changes['cost'] - cost_of_outputs
            outputs['add'].append((-1, values))

        return changes

    @fields.depends('disassembly')
    def on_change_product(self):
        return super(Production, self).on_change_product()

    @fields.depends('disassembly')
    def on_change_bom(self):
        return super(Production, self).on_change_bom()

    @fields.depends('disassembly')
    def on_change_uom(self):
        return super(Production, self).on_change_uom()

    @fields.depends('disassembly')
    def on_change_quantity(self):
        return super(Production, self).on_change_quantity()

    @fields.depends(*BOM_CHANGES)
    def on_change_disassembly(self):
        return self.explode_bom()
