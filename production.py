# -*- coding: utf-8 -*-
"""
    production_disassembly.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from decimal import Decimal

from trytond.model import fields
from trytond.pool import Pool, PoolMeta
from trytond.pyson import Eval
from trytond.modules.production import production


__metaclass__ = PoolMeta
BOM_CHANGES = production.BOM_CHANGES + ['disassembly']


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
        Uom = pool.get('product.uom')
        Template = pool.get('product.template')
        Product = pool.get('product.product')

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
        for input_ in self.bom.outputs:
            quantity = input_.compute_quantity(factor)
            values = self._explode_move_values(
                storage_location, self.location, self.company, input_, quantity
            )
            if values:
                inputs['add'].append((-1, values))
                quantity = Uom.compute_qty(
                    input_.uom, quantity, input_.product.default_uom
                )
                changes['cost'] += (
                    Decimal(str(quantity)) * input_.product.cost_price
                )

        if hasattr(Product, 'cost_price'):
            digits = Product.cost_price.digits
        else:
            digits = Template.cost_price.digits

        for output in self.bom.inputs:
            quantity = output.compute_quantity(factor)
            values = self._explode_move_values(
                self.location, storage_location, self.company, output, quantity
            )
            if values:
                values['unit_price'] = Decimal(0)
                if output.product.id == values.get('product') and quantity:
                    values['unit_price'] = Decimal(
                        changes['cost'] / Decimal(str(quantity))
                    ).quantize(Decimal(str(10 ** -digits[1])))
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
