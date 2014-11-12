# -*- coding: utf-8 -*-
"""
    tests/test_product.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import unittest
import time
from decimal import Decimal

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT
from trytond.transaction import Transaction
from trytond.config import CONFIG

CONFIG['elastic_search_server'] = "http://localhost:9200"


class TestProduct(unittest.TestCase):
    "Test Product"

    def setUp(self):
        """
        Set up data used in the tests.
        this method is called before each test function execution.
        """
        trytond.tests.test_tryton.install_module(
            'nereid_webshop_elastic_search'
        )

        self.ProductTemplate = POOL.get('product.template')
        self.Uom = POOL.get('product.uom')
        self.ProductCategory = POOL.get('product.category')
        self.Product = POOL.get('product.product')
        self.IndexBacklog = POOL.get('elasticsearch.index_backlog')
        self.PriceList = POOL.get('product.price_list')
        self.Party = POOL.get('party.party')
        self.Company = POOL.get('company.company')
        self.User = POOL.get('res.user')
        self.Currency = POOL.get('currency.currency')

    def create_products(self):
        """
        Returns two products
        """
        category, = self.ProductCategory.create([{
            'name': 'Test Category',
            'uri': 'test-category',
        }])
        uom, = self.Uom.search([('symbol', '=', 'u')])

        template1, template2 = self.ProductTemplate.create([
            {
                'name': 'Product 1',
                'type': 'goods',
                'category': category.id,
                'default_uom': uom.id,
                'description': 'This is product 1',
                'list_price': 5000,
                'cost_price': 4000,
            },
            {
                'name': 'Product 2',
                'type': 'goods',
                'category': category.id,
                'default_uom': uom.id,
                'description': 'This is product 2',
                'list_price': 3000,
                'cost_price': 2000,
            }
        ])

        return self.Product.create([
            {
                'template': template1,
                'code': 'code of product 1',
            },
            {
                'template': template2,
                'code': 'code of product 2',
            }
        ])

    def _create_pricelists(self):
        """
        Create the pricelists
        """
        # Setup the pricelists
        self.party_pl_margin = Decimal('1')
        self.guest_pl_margin = Decimal('1')
        user_price_list, = self.PriceList.create([{
            'name': 'PL 1',
            'company': self.company.id,
            'lines': [
                ('create', [{
                    'formula': 'unit_price * %s' % self.party_pl_margin
                }])
            ],
        }])
        guest_price_list, = self.PriceList.create([{
            'name': 'PL 2',
            'company': self.company.id,
            'lines': [
                ('create', [{
                    'formula': 'unit_price * %s' % self.guest_pl_margin
                }])
            ],
        }])
        return guest_price_list.id, user_price_list.id

    def setup_defaults(self):
        """
        Setup defaults
        """
        usd, = self.Currency.create([{
            'name': 'US Dollar',
            'code': 'USD',
            'symbol': '$',
        }])

        with Transaction().set_context(company=None):
            company_party, = self.Party.create([{
                'name': 'Openlabs',
                'addresses': [('create', [{
                    'name': 'Openlabs',
                }])],
            }])

        self.company, = self.Company.create([{
            'party': company_party.id,
            'currency': usd,
        }])

        self.User.write([self.User(USER)], {
            'company': self.company,
            'main_company': self.company,
        })

        # Create pricelists
        self._create_pricelists()

    def test_0010_test_product_indexing(self):
        """
        Tests indexing on creation and updation of product
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):

            self.setup_defaults()

            category_automobile, = self.ProductCategory.create([{
                'name': 'Automobile',
                'uri': 'automobile',
            }])
            uom, = self.Uom.search([('symbol', '=', 'u')])

            template, = self.ProductTemplate.create([{
                'name': 'Bat Mobile',
                'type': 'goods',
                'list_price': 50000,
                'cost_price': 40000,
                'category': category_automobile.id,
                'default_uom': uom.id,
            }])
            product, = self.Product.create([{
                'template': template,
                'code': 'Batman has a code',
                'use_template_description': False,
            }])
            self.assertEqual(self.IndexBacklog.search([], count=True), 1)
            # Clear backlog list
            self.IndexBacklog.delete(self.IndexBacklog.search([]))
            self.assertEqual(self.IndexBacklog.search([], count=True), 0)
            # Update the product
            self.ProductTemplate.write([product], {
                'description': "Batman's ride",
            })
            self.assertEqual(self.IndexBacklog.search([], count=True), 1)

            # Create two new products
            product1, product2 = self.create_products()

            # Update index on Elastic-Search server
            self.IndexBacklog.update_index()
            time.sleep(2)

            # Test if new records have been uploaded on elastic server
            # If Index Backlog if empty, it means the records have been updated
            self.assertEqual(self.IndexBacklog.search([], count=True), 0)


def suite():
    """
    Define suite
    """
    test_suite = trytond.tests.test_tryton.suite()
    test_suite.addTests(
        unittest.TestLoader().loadTestsFromTestCase(TestProduct)
    )
    return test_suite

if __name__ == '__main__':
    unittest.TextTestRunner(verbosity=2).run(suite())
