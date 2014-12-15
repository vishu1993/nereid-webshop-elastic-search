# -*- coding: utf-8 -*-
'''
    website

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from trytond.pool import Pool, PoolMeta

__metaclass__ = PoolMeta
__all__ = ['Website']


class Website:
    "Nereid Website"
    __name__ = 'nereid.website'

    @classmethod
    def auto_complete(cls, phrase, limit=10):
        """
        This is a downstream implementation which uses elasticsearch to return
        results for a query.
        """
        Product = Pool().get('product.product')

        return Product.elasticsearch_auto_complete(phrase, limit)
