# -*- coding: utf-8 -*-
"""
    product.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from trytond.pool import Pool, PoolMeta
from trytond.transaction import Transaction
from trytond.model import fields
from nereid import route, request, render_template
from nereid.contrib.pagination import Pagination
from pyes import BoolQuery, MatchQuery, NestedQuery

__metaclass__ = PoolMeta
__all__ = ['Product', 'Template']


class Product:
    __name__ = 'product.product'

    def elastic_search_json(self):
        """
        Return a JSON serializable dictionary
        """
        PriceList = Pool().get('product.price_list')
        User = Pool().get('res.user')

        if self.use_template_description:
            description = self.template.description
        else:  # pragma: no cover
            description = self.description

        price_lists = PriceList.search([])
        price_list_data = []

        company = User(Transaction().user).company

        for _list in price_lists:
            price_list_data.append({
                'id': _list.id,
                'price': _list.compute(
                    company.party, self, self.list_price, 1,
                    self.default_uom
                )
            })

        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'description': description,
            'list_price': self.list_price,
            'category': {
                'id': self.category.id,
                'name': self.category.name,
            } if self.category else {},
            'tree_nodes': [{
                'id': node.id,
                'name': node.node.name,
                'sequence': node.sequence,
            } for node in self.nodes],
            'type': self.type,
            'price_lists': price_list_data,
            'displayed_on_eshop': (
                "true" if self.displayed_on_eshop else "false"
            ),
            'active': "true" if self.active else "false",
            'attributes': self.get_elastic_filterable_data(),
        }

    def get_elastic_filterable_data(self):
        """
        This method returns a dictionary of attributes which will be used to
        filter search results. By default, it returns a product's attributes.
        Downstream modules can override this method to add any other relevant
        fields. This data is added to the index.
        """
        return self.attributes

    @classmethod
    def get_filterable_attributes(cls):
        """
        This method returns a list of filterable product attributes, which can
        be used in faceting and aggregation. Downstream modules can override
        this method to add any extra filterable fields.
        """
        Attribute = Pool().get('product.attribute')

        return [
            x.name for x in Attribute.search([('filterable', '=', True)])
        ]

    @classmethod
    def add_faceting_to_query(cls, query):
        """
        This method wraps the query by a `~pyes.query.Search` object, and then
        adds appropriate terms to the `facet` attribute of this object. By
        default, term facets are generated over filterable attributes.
        """
        filterable_attributes = cls.get_filterable_attributes()

        search_query = query.search()

        for attribute in filterable_attributes:
            search_query.facet.add_term_facet(attribute)

        return search_query

    @classmethod
    def get_elastic_search_query(cls, search_phrase):
        """
        Return an instance of `~pyes.query.Query` for the given phrase.
        If downstream modules wish to alter the behavior of search, for example
        by adding more fields to the query or changing the ranking in a
        different way, this would be the method to change.
        """
        return BoolQuery(
            should=[
                MatchQuery(
                    'code', search_phrase, boost=1.5
                ),
                MatchQuery(
                    'name', search_phrase, boost=2
                ),
                MatchQuery(
                    'name.partial', search_phrase
                ),
                MatchQuery(
                    'name.metaphone', search_phrase
                ),
                MatchQuery(
                    'description', search_phrase, boost=0.5
                ),
                MatchQuery(
                    'category.name', search_phrase
                ),
                NestedQuery(
                    'tree_nodes', BoolQuery(
                        should=[
                            MatchQuery(
                                'tree_nodes.name',
                                search_phrase
                            ),
                        ]
                    )
                ),
            ],
            must=[
                MatchQuery(
                    'active', "true"
                ),
                MatchQuery(
                    'displayed_on_eshop', "true"
                ),
            ]
        )

    @classmethod
    def search_on_elastic_search(cls, search_phrase, limit=100):
        """
        Searches on elasticsearch server for given search phrase.

        TODO:

            * Add support for sorting
            * Add support for aggregates

        This method passes a query, alongwith term facets, to the search method
        for processing. For example, if one has a `~pyes.query.BoolQuery`
        object, and the product has attributes 'color' and 'size', one may pass
        them as terms as follows -:

        >>> query.facet.add_term_facet('color')
        >>> query.facet.add_term_facet('size')

        The resultset is then obtained and relevant data can be retrieved.

        >>> result_set = conn.search(query, **kwargs)
        >>> print result_set.facets['color']['terms']
        [
            {'count': 1, 'term': 'blue'},
            {'count': 2, 'term': 'black'},
            ...
        ]

        :param search_phrase: Searches for this particular phrase
        :param limit: The number of records to be returned
        :returns: `~pyes.es.ResultSet` object which contains each product's
        attributes
        """
        config = Pool().get('elasticsearch.configuration')(1)

        conn = config.get_es_connection(timeout=5)
        query = cls.get_elastic_search_query(search_phrase)
        faceted_query = cls.add_faceting_to_query(query)

        return conn.search(
            faceted_query,
            doc_types=[config.make_type_name('product.product')],
            size=limit
        )

    @classmethod
    @route('/search')
    def quick_search(cls):
        """
        This version of quick_search uses elasticsearch to build
        search results for searches from the website.
        """
        page = request.args.get('page', 1, type=int)
        phrase = request.args.get('q', '')

        logger = Pool().get('elasticsearch.configuration').get_logger()

        result_set = cls.search_on_elastic_search(phrase)

        results = [
            r.id for r in
            result_set
        ]

        if not results:
            logger.info(
                "Search for %s yielded no results from elasticsearch." % phrase
            )
            logger.info("Falling back to parent quick_search.")
            return super(Product, cls).quick_search()

        logger.info(
            "Search for %s yielded in %d results." %
            (phrase, len(results))
        )

        products = Pagination(cls, [
            ('id', 'in', results),
        ], page, cls.per_page)

        return render_template('search-results.jinja', products=products)

    @classmethod
    def elasticsearch_auto_complete(cls, phrase, limit=10):
        """
        Handler for auto-completion via elastic-search.
        """
        results = []
        for product in cls.search_on_elastic_search(phrase, limit=limit):
            results.append({"value": product.name})

        return results


class Template:
    __name__ = 'product.template'

    @classmethod
    def create(cls, vlist):
        """
        Create a record in elastic search on create
        :param vlist: List of dictionaries of fields with values
        """
        IndexBacklog = Pool().get('elasticsearch.index_backlog')
        Product = Pool().get('product.product')

        templates = super(Template, cls).create(vlist)
        products = []
        for template in templates:
            products.extend([Product(p) for p in template.products])
        IndexBacklog.create_from_records(products)
        return templates

    @classmethod
    def write(cls, templates, values, *args):
        """
        Create a record in elastic search on write
        """
        IndexBacklog = Pool().get('elasticsearch.index_backlog')
        Product = Pool().get('product.product')

        rv = super(Template, cls).write(templates, values, *args)

        products = []
        for template in templates:
            products.extend([Product(p) for p in template.products])
        IndexBacklog.create_from_records(products)
        return rv


class ProductAttribute:
    __name__ = 'product.attribute'
    filterable = fields.Boolean('Filterable')

    @staticmethod
    def default_filterable():
        return True
