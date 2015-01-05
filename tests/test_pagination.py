# -*- coding: utf-8 -*-
"""
    tests/test_pagination.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
import time
import datetime
from dateutil.relativedelta import relativedelta
from decimal import Decimal
from pyes.managers import Indices

import trytond.tests.test_tryton
from trytond.tests.test_tryton import POOL, USER, DB_NAME, CONTEXT
from trytond.transaction import Transaction
from trytond.config import CONFIG
from nereid.testing import NereidTestCase
from pagination import ElasticPagination

CONFIG['elastic_search_server'] = "http://localhost:9200"


class TestPagination(NereidTestCase):
    """
    Test Pagination
    """
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
        self.FiscalYear = POOL.get('account.fiscalyear')
        self.Account = POOL.get('account.account')
        self.PaymentTerm = POOL.get('account.invoice.payment_term')
        self.Sale = POOL.get('sale.sale')
        self.Language = POOL.get('ir.lang')
        self.NereidWebsite = POOL.get('nereid.website')
        self.SaleShop = POOL.get('sale.shop')
        self.Country = POOL.get('country.country')
        self.Subdivision = POOL.get('country.subdivision')
        self.NereidUser = POOL.get('nereid.user')
        self.Location = POOL.get('stock.location')
        self.Locale = POOL.get('nereid.website.locale')
        self.Node = POOL.get('product.tree_node')
        self.ElasticConfig = POOL.get('elasticsearch.configuration')
        self.ElasticDocumentType = POOL.get('elasticsearch.document.type')

    def _create_fiscal_year(self, date=None, company=None):
        """
        Creates a fiscal year and requried sequences
        """
        Sequence = POOL.get('ir.sequence')
        SequenceStrict = POOL.get('ir.sequence.strict')

        if date is None:
            date = datetime.date.today()

        if company is None:
            company, = self.Company.search([], limit=1)

        invoice_sequence, = SequenceStrict.create([{
            'name': '%s' % date.year,
            'code': 'account.invoice',
            'company': company,
        }])
        fiscal_year, = self.FiscalYear.create([{
            'name': '%s' % date.year,
            'start_date': date + relativedelta(month=1, day=1),
            'end_date': date + relativedelta(month=12, day=31),
            'company': company,
            'post_move_sequence': Sequence.create([{
                'name': '%s' % date.year,
                'code': 'account.move',
                'company': company,
            }])[0],
            'out_invoice_sequence': invoice_sequence,
            'in_invoice_sequence': invoice_sequence,
            'out_credit_note_sequence': invoice_sequence,
            'in_credit_note_sequence': invoice_sequence,
        }])
        self.FiscalYear.create_period([fiscal_year])
        return fiscal_year

    def _create_coa_minimal(self, company):
        """Create a minimal chart of accounts
        """
        AccountTemplate = POOL.get('account.account.template')
        account_create_chart = POOL.get(
            'account.create_chart', type="wizard")

        account_template, = AccountTemplate.search(
            [('parent', '=', None)]
        )

        session_id, _, _ = account_create_chart.create()
        create_chart = account_create_chart(session_id)
        create_chart.account.account_template = account_template
        create_chart.account.company = company
        create_chart.transition_create_account()

        receivable, = self.Account.search([
            ('kind', '=', 'receivable'),
            ('company', '=', company),
        ])
        payable, = self.Account.search([
            ('kind', '=', 'payable'),
            ('company', '=', company),
        ])
        create_chart.properties.company = company
        create_chart.properties.account_receivable = receivable
        create_chart.properties.account_payable = payable
        create_chart.transition_create_properties()

    def _create_payment_term(self):
        """Create a simple payment term with all advance
        """

        return self.PaymentTerm.create([{
            'name': 'Direct',
            'lines': [('create', [{'type': 'remainder'}])]
        }])

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

    def _get_account_by_kind(self, kind, company=None, silent=True):
        """Returns an account with given spec
        :param kind: receivable/payable/expense/revenue
        :param silent: dont raise error if account is not found
        """

        if company is None:
            company, = self.Company.search([], limit=1)

        accounts = self.Account.search([
            ('kind', '=', kind),
            ('company', '=', company)
        ], limit=1)
        if not accounts and not silent:
            raise Exception("Account not found")
        return accounts[0] if accounts else False

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

        CONTEXT.update(self.User.get_preferences(context_only=True))

        # Create Fiscal Year
        self._create_fiscal_year(company=self.company.id)
        # Create Chart of Accounts
        self._create_coa_minimal(company=self.company.id)
        # Create a payment term
        payment_term, = self._create_payment_term()

        shop_price_list, user_price_list = self._create_pricelists()
        party1, = self.Party.create([{
            'name': 'Guest User',
        }])

        party2, = self.Party.create([{
            'name': 'Registered User',
            'sale_price_list': user_price_list,
        }])

        self.party2 = party2

        party3, = self.Party.create([{
            'name': 'Registered User 2',
        }])

        # Create users and assign the pricelists to them
        self.guest_user, = self.NereidUser.create([{
            'party': party1.id,
            'display_name': 'Guest User',
            'email': 'guest@openlabs.co.in',
            'password': 'password',
            'company': self.company.id,
        }])
        self.registered_user, = self.NereidUser.create([{
            'party': party2.id,
            'display_name': 'Registered User',
            'email': 'email@example.com',
            'password': 'password',
            'company': self.company.id,
        }])
        self.registered_user2, = self.NereidUser.create([{
            'party': party3.id,
            'display_name': 'Registered User 2',
            'email': 'email2@example.com',
            'password': 'password2',
            'company': self.company.id,
        }])

        warehouse, = self.Location.search([
            ('type', '=', 'warehouse')
        ], limit=1)
        location, = self.Location.search([
            ('type', '=', 'storage')
        ], limit=1)
        en_us, = self.Language.search([('code', '=', 'en_US')])

        self.locale_en_us, = self.Locale.create([{
            'code': 'en_US',
            'language': en_us.id,
            'currency': usd.id,
        }])

        self.shop, = self.SaleShop.create([{
            'name': 'Default Shop',
            'price_list': shop_price_list,
            'warehouse': warehouse,
            'payment_term': payment_term,
            'company': self.company.id,
            'users': [('add', [USER])]
        }])
        self.User.set_preferences({'shop': self.shop})

        self.default_node, = self.Node.create([{
            'name': 'root',
            'slug': 'root',
        }])
        self.country, = self.Country.create([{
            'name': 'United States',
            'code': 'US',
        }])
        self.subdivision1, = self.Subdivision.create([{
            'country': self.country.id,
            'name': 'California',
            'code': 'US-CA',
            'type': 'state',
        }])
        self.NereidWebsite.create([{
            'name': 'localhost',
            'shop': self.shop,
            'company': self.company.id,
            'application_user': USER,
            'default_locale': self.locale_en_us.id,
            'guest_user': self.guest_user,
            'countries': [('add', [self.country.id])],
            'currencies': [('add', [usd.id])],
        }])

    def clear_server(self):
        """
        Clear the elasticsearch server.
        """
        conn = self.ElasticConfig(1).get_es_connection()
        index_name = self.ElasticConfig(1).get_index_name(name=None)

        indices = Indices(conn)
        indices.delete_index_if_exists(index_name)

    def update_treenode_mapping(self):
        """
        Update tree_nodes mapping as nested.
        """
        product_doc, = self.ElasticDocumentType.search([])
        self.ElasticConfig.update_settings([self.ElasticConfig(1)])
        self.ElasticDocumentType.update_mapping([product_doc])

    def test_0010_elastic_pagination(self):
        """
        Tests the basic usage of ElasticPagination
        """
        with Transaction().start(DB_NAME, USER, context=CONTEXT):
            self.update_treenode_mapping()

            category, = self.ProductCategory.create([{
                'name': 'Test Category',
                'uri': 'test-category',
            }])
            uom, = self.Uom.search([('symbol', '=', 'u')])
            template, = self.ProductTemplate.create([{
                'name': 'GreatProduct',
                'type': 'goods',
                'category': category.id,
                'default_uom': uom.id,
                'description': 'This is a product',
                'list_price': Decimal(3000),
                'cost_price': Decimal(2000),
            }])

            # Create a hundred product variants
            for x in range(0, 100):
                self.Product.create([{
                    'template': template.id,
                    'code': 'code_' + str(x),
                    'displayed_on_eshop': True,
                    'uri': 'prod_' + str(x)
                }])

            self.IndexBacklog.update_index()
            time.sleep(5)

            self.assertEqual(self.IndexBacklog.search([], count=True), 0)

            search_obj = self.Product.search_on_elastic_search('GreatProduct')

            pagination = ElasticPagination(
                self.Product.__name__, search_obj, page=1, per_page=10
            )

            self.assertEqual(pagination.count, 100)
            self.assertEqual(pagination.pages, 10)
            self.assertEqual(pagination.begin_count, 1)
            self.assertEqual(pagination.end_count, 10)

            self.clear_server()
