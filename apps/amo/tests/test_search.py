from nose.tools import eq_

import amo.tests
from addons.models import Addon


class TestES(amo.tests.ESTestCase):
    es = True

    # This should go in a test for the cron.
    def test_indexed_count(self):
        # Did all the right addons get indexed?
        eq_(Addon.search().filter(type=1, is_disabled=False).count(),
            Addon.objects.filter(disabled_by_user=False,
                                 status__in=amo.VALID_STATUSES).count())

    def test_clone(self):
        # Doing a filter creates a new ES object.
        qs = Addon.search()
        qs2 = qs.filter(type=1)
        eq_(qs._build_query(), {'fields': ['id']})
        eq_(qs2._build_query(), {'fields': ['id'],
                                 'filter': {'term': {'type': 1}}})

    def test_filter(self):
        qs = Addon.search().filter(type=1)
        eq_(qs._build_query(), {'fields': ['id'],
                                'filter': {'term': {'type': 1}}})

    def test_in_filter(self):
        qs = Addon.search().filter(type__in=[1, 2])
        eq_(qs._build_query(), {'fields': ['id'],
                                'filter': {'in': {'type': [1, 2]}}})

    def test_and(self):
        qs = Addon.search().filter(type=1, category__in=[1, 2])
        eq_(qs._build_query(), {'fields': ['id'],
                                'filter': {'and': [
                                    {'term': {'type': 1}},
                                    {'in': {'category': [1, 2]}},
                                ]}})

    def test_query(self):
        qs = Addon.search().query(type=1)
        eq_(qs._build_query(), {'fields': ['id'],
                                'query': {'term': {'type': 1}}})

    def test_order_by_desc(self):
        qs = Addon.search().order_by('-rating')
        eq_(qs._build_query(), {'fields': ['id'],
                                'sort': [{'rating': 'desc'}]})

    def test_order_by_asc(self):
        qs = Addon.search().order_by('rating')
        eq_(qs._build_query(), {'fields': ['id'],
                                'sort': ['rating']})

    def test_order_by_multiple(self):
        qs = Addon.search().order_by('-rating', 'id')
        eq_(qs._build_query(), {'fields': ['id'],
                                'sort': [{'rating': 'desc'}, 'id']})

    def test_slice(self):
        qs = Addon.search()[5:12]
        eq_(qs._build_query(), {'fields': ['id'],
                                'from': 5,
                                'size': 7})

    def test_or(self):
        qs = Addon.search().filter(type=1).filter_or(status=1, app=2)
        eq_(qs._build_query(), {'fields': ['id'],
                                'filter': {'and': [
                                    {'term': {'type': 1}},
                                    {'or': [{'term': {'status': 1}},
                                            {'term': {'app': 2}}]},
                                ]}})

    def test_slice_stop(self):
        qs = Addon.search()[:6]
        eq_(qs._build_query(), {'fields': ['id'],
                                'size': 6})

    def test_getitem(self):
        addons = list(Addon.search())
        eq_(addons[0], Addon.search()[0])

    def test_iter(self):
        qs = Addon.search().filter(type=1, is_disabled=False)
        eq_(len(qs), 4)
        eq_(len(list(qs)), 4)

    def test_count(self):
        eq_(Addon.search().count(), 6)

    def test_len(self):
        qs = Addon.search()
        qs._results_cache = [1]
        eq_(len(qs), 1)

    def test_gte(self):
        qs = Addon.search().filter(type__in=[1, 2], status__gte=4)
        eq_(qs._build_query(), {'fields': ['id'],
                                'filter': {'and': [
                                    {'in': {'type': [1, 2]}},
                                    {'range': {'status': {'gte': 4}}},
                                ]}})

    def test_lte(self):
        qs = Addon.search().filter(type__in=[1, 2], status__lte=4)
        eq_(qs._build_query(), {'fields': ['id'],
                                'filter': {'and': [
                                    {'in': {'type': [1, 2]}},
                                    {'range': {'status': {'lte': 4}}},
                                ]}})

    def test_gt(self):
        qs = Addon.search().filter(type__in=[1, 2], status__gt=4)
        eq_(qs._build_query(), {'fields': ['id'],
                                'filter': {'and': [
                                    {'in': {'type': [1, 2]}},
                                    {'range': {'status': {'gt': 4}}},
                                ]}})

    def test_lt(self):
        qs = Addon.search().filter(type__in=[1, 2], status__lt=4)
        eq_(qs._build_query(), {'fields': ['id'],
                                'filter': {'and': [
                                    {'range': {'status': {'lt': 4}}},
                                    {'in': {'type': [1, 2]}},
                                ]}})

    def test_lt2(self):
        qs = Addon.search().filter(status__lt=4)
        eq_(qs._build_query(), {'fields': ['id'],
                                'filter': {'range': {'status': {'lt': 4}}}})

    def test_prefix(self):
        qs = Addon.search().query(name__startswith='woo')
        eq_(qs._build_query(), {'fields': ['id'],
                                'query': {'prefix': {'name': 'woo'}}})

    def test_values(self):
        qs = Addon.search().values('name')
        eq_(qs._build_query(), {'fields': ['id', 'name']})

    def test_values_result(self):
        qs = Addon.objects.order_by('id')
        addons = [(a.id, unicode(a.name)) for a in qs]
        qs = Addon.search().values('name').order_by('id')
        eq_(list(qs), addons)

    def test_values_dict(self):
        qs = Addon.search().values_dict('name')
        eq_(qs._build_query(), {'fields': ['id', 'name']})

    def test_values_dict_result(self):
        qs = Addon.objects.order_by('id')
        addons = [{'id': a.id, 'name': unicode(a.name)} for a in qs]
        qs = Addon.search().values_dict('name').order_by('id')
        eq_(list(qs), list(addons))

    def test_object_result(self):
        addons = Addon.objects.all()[:1]
        qs = Addon.search().filter(id=addons[0].id)[:1]
        eq_(list(addons), list(qs))

    def test_object_result_slice(self):
        addon = Addon.objects.all()[0]
        qs = Addon.search().filter(id=addon.id)
        eq_(addon, qs[0])
