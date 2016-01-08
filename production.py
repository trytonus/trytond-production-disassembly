# -*- coding: utf-8 -*-
from decimal import Decimal
from collections import namedtuple

from trytond.model import ModelView, fields
from trytond.pool import PoolMeta
from trytond.pyson import Eval
from trytond.pool import Pool


__metaclass__ = PoolMeta
__all__ = ['Production', 'Configuration']


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
        'Disassembled?', states={
            'readonly': ~Eval('state').in_(['request', 'draft']),
            'invisible': ~Eval('product'),
        }, readonly=True, depends=['product']
    )

    @classmethod
    def __setup__(cls):
        super(Production, cls).__setup__()
        cls._buttons.update({
            'disassemble': {
                'invisible': Eval('state') != 'draft',
            }
        })

    def _disassemble(self):
        "Disassembly inverts outputs and inputs"
        Configuration = Pool().get('production.configuration')
        Production = Pool().get('production')

        if self.disassembly:
            return

        bom_inputs, bom_outputs = self.bom.outputs, self.bom.inputs
        self.disassembly = True

        factor = self.bom.compute_factor(
            self.product, self.quantity or 0, self.uom
        )

        storage_location = self.warehouse.storage_location

        def clean_field_names(data):
            for key in data.keys():
                if "." in key:
                    del data[key]
            return data

        new_inputs = []
        for input_ in bom_inputs:
            quantity = input_.compute_quantity(factor)
            values = self._explode_move_values(
                storage_location, self.location, self.company, input_, quantity
            )
            if values:
                self.cost += (
                    Decimal(str(quantity)) * input_.product.cost_price
                )
                new_inputs.append(clean_field_names(values))

        cost_of_outputs = Decimal('0')
        new_outputs = []
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
                new_outputs.append(clean_field_names(values))

        if not self.company.currency.is_zero(self.cost - cost_of_outputs):
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
            values['unit_price'] = self.cost - cost_of_outputs
            new_outputs.append(clean_field_names(values))

        inputs_to_delete = map(int, self.inputs)
        outputs_to_delete = map(int, self.outputs)
        Production.write([self], {
            'disassembly': True,
            'cost': self.cost,
            'inputs': [
                ('create', new_inputs),
                ('remove', inputs_to_delete)
            ],
            'outputs': [
                ('create', new_outputs),
                ('remove', outputs_to_delete)
            ]
        })

    @classmethod
    @ModelView.button
    def disassemble(cls, productions):
        for production in productions:
            if production.state != "draft":
                continue
            production._disassemble()
