# -*- coding: utf-8 -*-
"""
    __init__.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool
from product import Product, Template


def register():
    Pool.register(
        Product,
        Template,
        module='nereid_webshop_elastic_search', type_='model'
    )
