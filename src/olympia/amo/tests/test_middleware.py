from django import test
from django.core.exceptions import ImproperlyConfigured
from django.http import HttpResponse
from django.test.client import RequestFactory
from django.test.utils import override_settings
from django.urls import reverse

import pytest

from unittest.mock import patch
from pyquery import PyQuery as pq

from olympia.amo.middleware import (
    AuthenticationMiddlewareWithoutAPI,
    CacheControlMiddleware,
    RequestIdMiddleware,
    SetRemoteAddrFromForwardedFor,
)
from olympia.amo.tests import reverse_ns, TestCase
from olympia.zadmin.models import Config


pytestmark = pytest.mark.django_db


class TestMiddleware(TestCase):
    def test_no_vary_cookie(self):
        # Requesting / forces a Vary on Accept-Language on User-Agent, since
        # we redirect to /<lang>/<app>/.
        response = test.Client().get('/pages/appversions/')
        assert response['Vary'] == 'Accept-Language, User-Agent'

        # Only Vary on Accept-Encoding after that (because of gzip middleware).
        # Crucially, we avoid Varying on Cookie.
        response = test.Client().get('/pages/appversions/', follow=True)
        assert response['Vary'] == 'Accept-Encoding'

    @patch('django.contrib.auth.middleware.AuthenticationMiddleware.process_request')
    def test_authentication_used_outside_the_api(self, process_request):
        req = RequestFactory().get('/')
        req.is_api = False
        AuthenticationMiddlewareWithoutAPI().process_request(req)
        assert process_request.called

    @patch('django.contrib.sessions.middleware.SessionMiddleware.process_request')
    def test_authentication_not_used_with_the_api(self, process_request):
        req = RequestFactory().get('/')
        req.is_api = True
        AuthenticationMiddlewareWithoutAPI().process_request(req)
        assert not process_request.called

    @patch('django.contrib.auth.middleware.AuthenticationMiddleware.process_request')
    def test_authentication_is_used_with_accounts_auth(self, process_request):
        req = RequestFactory().get('/api/v3/accounts/authenticate/')
        req.is_api = True
        AuthenticationMiddlewareWithoutAPI().process_request(req)
        assert process_request.call_count == 1

        req = RequestFactory().get('/api/v4/accounts/authenticate/')
        req.is_api = True
        AuthenticationMiddlewareWithoutAPI().process_request(req)
        assert process_request.call_count == 2

        req = RequestFactory().get('/api/v5/accounts/authenticate/')
        req.is_api = True
        AuthenticationMiddlewareWithoutAPI().process_request(req)
        assert process_request.call_count == 3


def test_redirect_with_unicode_get():
    response = test.Client().get(
        '/da/firefox/addon/5457?from=/da/firefox/'
        'addon/5457%3Fadvancedsearch%3D1&lang=ja&utm_source=Google+%E3'
        '%83%90%E3%82%BA&utm_medium=twitter&utm_term=Google+%E3%83%90%'
        'E3%82%BA'
    )
    assert response.status_code == 302
    assert 'utm_term=Google+%E3%83%90%E3%82%BA' in response['Location']


def test_source_with_wrong_unicode_get():
    # The following url is a string (bytes), not unicode.
    response = test.Client().get(
        '/firefox/collections/mozmj/autumn/?source=firefoxsocialmedia\x14\x85'
    )
    assert response.status_code == 302
    assert response['Location'].endswith('?source=firefoxsocialmedia%14%C3%82%C2%85')


def test_trailing_slash_middleware():
    response = test.Client().get('/en-US/about/?xxx=\xc3')
    assert response.status_code == 301
    assert response['Location'].endswith('/en-US/about?xxx=%C3%83%C2%83')


class AdminMessageTest(TestCase):
    def test_message(self):
        c = Config.objects.create(key='site_notice', value='ET Sighted.')

        r = self.client.get(reverse('apps.appversions'), follow=True)
        doc = pq(r.content)
        assert doc('#site-notice').text() == 'ET Sighted.'

        c.delete()

        r = self.client.get(reverse('apps.appversions'), follow=True)
        doc = pq(r.content)
        assert len(doc('#site-notice')) == 0


class TestNoDjangoDebugToolbar(TestCase):
    """Make sure the Django Debug Toolbar isn't available when DEBUG=False."""

    def test_no_django_debug_toolbar(self):
        with self.settings(DEBUG=False):
            res = self.client.get(reverse('devhub.index'), follow=True)
            assert b'djDebug' not in res.content
            assert b'debug_toolbar' not in res.content


def test_request_id_middleware(client):
    """Test that we add a request id to every response"""
    response = client.get(reverse('devhub.index'))
    assert response.status_code == 200
    assert isinstance(response['X-AMO-Request-ID'], str)

    # Test that we set `request.request_id` too

    request = RequestFactory().get('/')
    RequestIdMiddleware().process_request(request)
    assert request.request_id


class TestSetRemoteAddrFromForwardedFor(TestCase):
    def setUp(self):
        self.middleware = SetRemoteAddrFromForwardedFor()

    def test_no_special_headers(self):
        request = RequestFactory().get('/', REMOTE_ADDR='4.8.15.16')
        assert not self.middleware.is_request_from_cdn(request)
        self.middleware.process_request(request)
        assert request.META['REMOTE_ADDR'] == '4.8.15.16'

    def test_request_not_from_cdn(self):
        request = RequestFactory().get(
            '/', REMOTE_ADDR='4.8.15.16', HTTP_X_FORWARDED_FOR='2.3.4.2,4.8.15.16'
        )
        assert not self.middleware.is_request_from_cdn(request)
        self.middleware.process_request(request)
        assert request.META['REMOTE_ADDR'] == '4.8.15.16'

    @override_settings(SECRET_CDN_TOKEN=None)
    def test_request_not_from_cdn_because_setting_is_none(self):
        request = RequestFactory().get(
            '/',
            REMOTE_ADDR='4.8.15.16',
            HTTP_X_FORWARDED_FOR='2.3.4.2,4.8.15.16',
            HTTP_X_REQUEST_VIA_CDN=None,
        )
        assert not self.middleware.is_request_from_cdn(request)
        self.middleware.process_request(request)
        assert request.META['REMOTE_ADDR'] == '4.8.15.16'

    @override_settings(SECRET_CDN_TOKEN='foo')
    def test_request_not_from_cdn_because_header_secret_is_invalid(self):
        request = RequestFactory().get(
            '/',
            REMOTE_ADDR='4.8.15.16',
            HTTP_X_FORWARDED_FOR='2.3.4.2,4.8.15.16',
            HTTP_X_REQUEST_VIA_CDN='not-foo',
        )
        assert not self.middleware.is_request_from_cdn(request)
        self.middleware.process_request(request)
        assert request.META['REMOTE_ADDR'] == '4.8.15.16'

    @override_settings(SECRET_CDN_TOKEN='foo')
    def test_request_from_cdn_but_only_one_ip_in_x_forwarded_for(self):
        request = RequestFactory().get(
            '/',
            REMOTE_ADDR='4.8.15.16',
            HTTP_X_FORWARDED_FOR='4.8.15.16',
            HTTP_X_REQUEST_VIA_CDN='foo',
        )
        assert self.middleware.is_request_from_cdn(request)
        with self.assertRaises(ImproperlyConfigured):
            self.middleware.process_request(request)

    @override_settings(SECRET_CDN_TOKEN='foo')
    def test_request_from_cdn_but_empty_values_in_x_forwarded_for(self):
        request = RequestFactory().get(
            '/',
            REMOTE_ADDR='4.8.15.16',
            HTTP_X_FORWARDED_FOR=',',
            HTTP_X_REQUEST_VIA_CDN='foo',
        )
        assert self.middleware.is_request_from_cdn(request)
        with self.assertRaises(ImproperlyConfigured):
            self.middleware.process_request(request)

    @override_settings(SECRET_CDN_TOKEN='foo')
    def test_request_from_cdn_pick_second_to_last_ip_in_x_forwarded_for(self):
        request = RequestFactory().get(
            '/',
            REMOTE_ADDR='4.8.15.16',
            HTTP_X_FORWARDED_FOR=',, 2.3.4.2,  4.8.15.16',
            HTTP_X_REQUEST_VIA_CDN='foo',
        )
        assert self.middleware.is_request_from_cdn(request)
        self.middleware.process_request(request)
        assert request.META['REMOTE_ADDR'] == '2.3.4.2'


class TestCacheControlMiddleware(TestCase):
    def setUp(self):
        self.request_factory = RequestFactory()

    def test_not_api_should_not_cache(self):
        request = self.request_factory.get('/bar')
        request.is_api = False
        response = HttpResponse()
        response = CacheControlMiddleware(lambda x: response)(request)
        assert response['Cache-Control'] == 's-maxage=0'

    def test_authenticated_should_not_cache(self):
        request = self.request_factory.get('/api/v5/foo')
        request.is_api = True
        request.META = {'HTTP_AUTHORIZATION': 'foo'}
        response = HttpResponse()
        response = CacheControlMiddleware(lambda x: response)(request)
        assert response['Cache-Control'] == 's-maxage=0'

    def test_non_read_only_http_method_should_not_cache(self):
        request = self.request_factory.get('/api/v5/foo')
        request.is_api = True
        for method in ('POST', 'DELETE', 'PUT', 'PATCH'):
            request.method = method
            response = HttpResponse()
            response = CacheControlMiddleware(lambda x: response)(request)
            assert response['Cache-Control'] == 's-maxage=0'

    def test_disable_caching_arg_should_not_cache(self):
        request = self.request_factory.get('/api/v5/foo')
        request.is_api = True
        request.GET = {'disable_caching': '1'}
        response = HttpResponse()
        response = CacheControlMiddleware(lambda x: response)(request)
        assert response['Cache-Control'] == 's-maxage=0'

    def test_cookies_in_response_should_not_cache(self):
        request = self.request_factory.get('/api/v5/foo')
        request.is_api = True
        response = HttpResponse()
        response.set_cookie('foo', 'bar')
        response = CacheControlMiddleware(lambda x: response)(request)
        assert response['Cache-Control'] == 's-maxage=0'

    def test_cache_control_already_set_should_not_override(self):
        request = self.request_factory.get('/api/v5/foo')
        request.is_api = True
        response = HttpResponse()
        response['Cache-Control'] = 'max-age=3600'
        response = CacheControlMiddleware(lambda x: response)(request)
        assert response['Cache-Control'] == 'max-age=3600'

    def test_cache_control_already_set_to_0_should_not_set_s_maxage(self):
        request = self.request_factory.get('/api/v5/foo')
        request.is_api = True
        response = HttpResponse()
        response['Cache-Control'] = 'max-age=0'
        response = CacheControlMiddleware(lambda x: response)(request)
        assert response['Cache-Control'] == 'max-age=0'

    def test_non_success_status_code_should_not_cache(self):
        request = self.request_factory.get('/api/v5/foo')
        request.is_api = True
        response = HttpResponse()
        for status_code in (400, 401, 403, 404, 429, 500, 502, 503, 504):
            response.status_code = status_code
            response = CacheControlMiddleware(lambda x: response)(request)
            assert response['Cache-Control'] == 's-maxage=0'

    def test_everything_ok_should_cache_for_3_minutes(self):
        request = self.request_factory.get('/api/v5/foo')
        request.is_api = True
        response = HttpResponse()
        for status_code in (200, 201, 202, 204, 301, 302, 303, 304):
            response.status_code = status_code
            response = CacheControlMiddleware(lambda x: response)(request)
            assert response['Cache-Control'] == 'max-age=180'

    def test_functional_should_cache(self):
        response = self.client.get(reverse_ns('amo-site-status'))
        assert response.status_code == 200
        assert 'Cache-Control' in response
        assert response['Cache-Control'] == 'max-age=180'

    def test_functional_should_not_cache(self):
        response = self.client.get(
            reverse_ns('amo-site-status'), HTTP_AUTHORIZATION='blah'
        )
        assert response.status_code == 200
        assert response['Cache-Control'] == 's-maxage=0'
