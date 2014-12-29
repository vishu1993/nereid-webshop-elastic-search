# -*- coding: utf-8 -*-
"""
    pagination.py

    :copyright: (c) 2015 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from nereid.contrib.pagination import BasePagination
from trytond.pool import Pool
from werkzeug.utils import cached_property


class ElasticPagination(BasePagination):
    """
    Specialized paginator class for Elasticsearch result sets. It takes a
    `~pyes.query.Search` object and performs the search using pagination
    capabilities.
    """
    def __init__(self, model, search_obj, page, per_page):
        """
        :param model: Name of the tryton model on which the pagination is
                      happening.
        :param search_obj: The `~pyes.query.Search` object
        :param page: The page number
        :param per_page: Items per page
        """
        self.model_name = model
        self.search_obj = search_obj
        super(ElasticPagination, self).__init__(page, per_page)

    @property
    def model(self):
        return Pool().get(self.model_name)

    @cached_property
    def result_set(self):
        """
        Generates the `~pyes.es.ResultSet` object after performing the search.
        """
        config = Pool().get('elasticsearch.configuration')(1)

        conn = config.get_es_connection(timeout=5)

        return conn.search(
            self.search_obj,
            start=self.offset,
            size=self.per_page,
            doc_types=[config.make_type_name(self.model_name)]
        )

    @property
    def count(self):
        """
        Returns the total count of matched records.
        """
        return self.result_set.count()

    def items(self):
        """
        Returns items on the current page.
        """
        return self.model.browse(
            map(lambda p: p.id, self.result_set)
        )

    def all_items(self):
        """
        Returns all items.
        """
        config = Pool().get('elasticsearch.configuration')(1)

        conn = config.get_es_connection(timeout=5)

        return self.model.browse(
            map(
                lambda p: p.id, conn.search(
                    self.search_obj,
                    doc_types=[
                        config.make_type_name(self.model_name)
                    ]
                )
            )
        )
