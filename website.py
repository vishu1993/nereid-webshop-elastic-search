# -*- coding: utf-8 -*-
'''
    website

    :copyright: (c) 2014-2015 by Openlabs Technologies & Consulting (P) Ltd.
    :license: GPLv3, see LICENSE for more details

'''
from trytond.pool import Pool, PoolMeta
from nereid import request, route, render_template
from pagination import ElasticPagination

__metaclass__ = PoolMeta
__all__ = ['Website']


class Website:
    "Nereid Website"
    __name__ = 'nereid.website'

    @classmethod
    def auto_complete(cls, phrase):
        """
        This is a downstream implementation which uses elasticsearch to return
        results for a query.
        """
        Product = Pool().get('product.product')

        return Product._es_autocomplete(phrase)

    @classmethod
    @route('/search')
    def quick_search(cls):
        """
        This version of quick_search uses elasticsearch to build
        search results for searches from the website.
        """
        Product = Pool().get('product.product')

        page = request.args.get('page', 1, type=int)
        phrase = request.args.get('q', '')

        logger = Pool().get('elasticsearch.configuration').get_logger()

        search_obj = Product._quick_search_es(phrase)

        products = ElasticPagination(
            Product.__name__, search_obj, page, Product.per_page
        )

        if products:
            logger.info(
                "Search for %s yielded in %d results." %
                (phrase, products.count)
            )
        else:
            logger.info(
                "Search for %s yielded no results from elasticsearch." % phrase
            )

        return render_template(
            'search-results.jinja',
            products=products,
            facets=products.result_set.facets
        )
