# -*- coding: utf-8 -*-
# kate: space-indent on; indent-width 4; replace-tabs on;

"""
 *  Copyright (C) 2010, Michael "Svedrin" Ziegler <diese-addy@funzt-halt.net>
 *
 *  djExtDirect is free software; you can redistribute it and/or modify
 *  it under the terms of the GNU General Public License as published by
 *  the Free Software Foundation; either version 2 of the License, or
 *  (at your option) any later version.
 *
 *  This package is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 *  GNU General Public License for more details.
"""

import json
import inspect
import functools
import six
import traceback
from sys import stderr

from django.http import HttpResponse
from django.conf import settings
from django.conf.urls import url, include
from django.core.urlresolvers import reverse
from django.utils.datastructures import MultiValueDictKeyError
from django.core.serializers.json import DjangoJSONEncoder

from . import json_str


def getname(cls_or_name):
    """ If cls_or_name is not a string, return its __name__. """
    if not isinstance(cls_or_name, six.string_types):
        return cls_or_name.__name__
    return cls_or_name


class Provider(object):
    """ Provider for Ext.Direct. This class handles building API information and
        routing requests to the appropriate functions, and serializing their
        response and exceptions - if any.

        Instantiation:

        >>> EXT_JS_PROVIDER = Provider(name="Ext.app.REMOTING_API", autoadd=True, timeout=30)

        If autoadd is True, the api.js will include a line like such::

            Ext.Direct.addProvider( Ext.app.REMOTING_API );

        The value of timeout is in seconds and will be converted to milliseconds
        when rendering api.js. Defaults to 0 (use ExtJS timeout)

        After instantiating the Provider, register functions to it like so:

        >>> @EXT_JS_PROVIDER.register_method("myclass")
        ... def myview( request, possibly, some, other, arguments ):
        ...    " does something with all those args and returns something "
        ...    return 13.37

        Note that those views **MUST NOT** return an HttpResponse but simply
        the plain result, as the Provider will build a response from whatever
        your view returns!

        To be able to access the Provider, include its URLs in an arbitrary
        URL pattern, like so:

        >>> from views import EXT_JS_PROVIDER # import our provider instance
        >>> urlpatterns = (
        ...     # other patterns go here
        ...     url( r'api/', include(EXT_DIRECT_PROVIDER.urls) ),
        ... )

        This way, the Provider will define the URLs "api/api.js" and "api/router".

        If you then access the "api/api.js" URL, you will get a response such as::

            Ext.app.REMOTING_API = { # Ext.app.REMOTING_API is from Provider.name
                "url": "/mumble/api/router",
                "type": "remoting",
                "actions": {"myclass": [{"name": "myview", "len": 4}]},
                "timeout": 30000
                }

        You can then use this code in ExtJS to define the Provider there.
    """

    def __init__(self, name="Ext.app.REMOTING_API", autoadd=True, timeout=0,
                 url_namespace=None, url_app=None, **config):
        self.name = name
        self.autoadd = autoadd
        self.timeout = timeout or 0
        self.classes = {}
        self.config = config

        self.url_app = url_app

        self._request_viewname = ''

        self.url_namespace = url_namespace
        if url_namespace:
            self._request_viewname += url_namespace + ':'

        self._request_viewname += 'router'

    @property
    def urlconf(self):
        return include(self.urls, self.url_namespace, self.url_app)

    def register_method(self, cls_or_name, flags=None):
        """ Return a function that takes a method as an argument and adds that
            to cls_or_name.

            The flags parameter is for additional information, e.g. formHandler=True.

            Note: This decorator does not replace the method by a new function,
            it returns the original function as-is.
        """
        return functools.partial(self._register_method, cls_or_name, flags=flags)

    def _register_method(self, cls_or_name, method, flags=None, unwrap_for_argnames=True, with_name=None):
        """ Actually registers the given function as a method of cls_or_name. """
        clsname = getname(cls_or_name)
        if clsname not in self.classes:
            self.classes[clsname] = {}
        if flags is None:
            flags = {}
        self.classes[clsname][with_name or method.__name__] = method

        if unwrap_for_argnames:
            unwrapped = method

            while hasattr(unwrapped, '__wrapped__'):
                unwrapped = unwrapped.__wrapped__

            arg_list = inspect.getargspec(unwrapped)[0]
        else:
            arg_list = inspect.getargspec(method)[0]

        try:
            method.EXT_argnames = arg_list[2 if arg_list[0] == 'self' else 1:]
        except IndexError:
            method.EXT_argnames = []

        method.EXT_len = len(method.EXT_argnames)
        method.EXT_flags = flags
        return method

    def build_api_dict(self):
        actdict = {}
        for clsname in self.classes:
            actdict[clsname] = []
            for methodname in self.classes[clsname]:
                methinfo = {
                    "name": methodname,
                    "len": self.classes[clsname][methodname].EXT_len
                }
                methinfo.update(self.classes[clsname][methodname].EXT_flags)
                actdict[clsname].append(methinfo)

        return actdict

    def get_api_plain(self, request):
        """ Introspect the methods and get a JSON description of only the API. """
        config = self.config.copy()
        config.update(
            url=reverse(self._request_viewname),
            type="remoting",
            actions=self.build_api_dict(),
            timeout=self.timeout * 1000
        )

        return HttpResponse(
            json.dumps(config, cls=DjangoJSONEncoder),
            content_type="application/json"
        )

    def get_api(self, request):
        """ Introspect the methods and get a javascript description of the API
            that is meant to be embedded directly into the web site.
        """
        request.META["CSRF_COOKIE_USED"] = True

        config = self.config.copy()
        config.update(
            url=reverse(self._request_viewname),
            type="remoting",
            actions=self.build_api_dict(),
            timeout=self.timeout * 1000
        )

        lines = ["%s = %s;" % (self.name, json.dumps(config, cls=DjangoJSONEncoder))]

        if self.autoadd:
            lines.append(
                """Ext.Ajax.on("beforerequest", function(conn, options){"""
                """    if( !options.headers )"""
                """        options.headers = {};"""
                """    options.headers["X-CSRFToken"] = Ext.util.Cookies.get("csrftoken");"""
                """});"""
            )
            lines.append("Ext.Direct.addProvider( %s );" % self.name)

        return HttpResponse("\n".join(lines), content_type="text/javascript")

    def request(self, request):
        """ Implements the Router part of the Ext.Direct specification.

            It handles decoding requests, calling the appropriate function (if
            found) and encoding the response / exceptions.
        """
        request.META["CSRF_COOKIE_USED"] = True
        request.META['ExtJSDirect'] = True
        # First try to use request.POST, if that doesn't work check for req.body.
        # The other way round this might make more sense because the case that uses
        # body is way more common, but accessing request.POST after body
        # causes issues with Django's test client while accessing body after
        # request.POST does not.
        try:
            jsoninfo = {
                'action': request.POST['extAction'],
                'method': request.POST['extMethod'],
                'type': request.POST['extType'],
                'upload': request.POST['extUpload'],
                'tid': request.POST['extTID'],
            }
        except (MultiValueDictKeyError, KeyError) as err:
            pass
        else:
            return self.process_form_request(request, jsoninfo)

        try:
            rawjson = json.loads(request.body.decode(request.encoding or 'UTF-8'))
        except getattr(json, "JSONDecodeError", ValueError) as _err:
            return HttpResponse(json.dumps({
                'type': 'exception',
                'message': 'malformed request',
                'where': str(_err),
                "tid": None,  # dunno
            }, cls=DjangoJSONEncoder), content_type="application/json")
        else:
            return self.process_normal_request(request, rawjson)

    def process_normal_request(self, request, rawjson):
        """ Process standard requests (no form submission or file uploads). """
        if not isinstance(rawjson, list):
            rawjson = [rawjson]

        responses = []
        replace_json_strs = []

        for reqinfo in rawjson:
            cls, methname, data, rtype, tid = (
                reqinfo['action'],
                reqinfo['method'],
                reqinfo['data'],
                reqinfo['type'],
                reqinfo['tid'],
            )

            if cls not in self.classes:
                responses.append({
                    'type': 'exception',
                    'message': 'no such action',
                    'where': cls,
                    "tid": tid,
                })
                continue

            if methname not in self.classes[cls]:
                responses.append({
                    'type': 'exception',
                    'message': 'no such method',
                    'where': methname,
                    "tid": tid,
                })
                continue

            func = self.classes[cls][methname]

            if func.EXT_len and len(data) == 1 and type(data[0]) == dict:
                # data[0] seems to contain a dict with params. check if it does, and if so, unpack
                args = []
                for argname in func.EXT_argnames:
                    if argname in data[0]:
                        args.append(data[0][argname])
                    else:
                        args = None
                        break
                if args:
                    data = args

            if data is not None:
                datalen = len(data)
            else:
                datalen = 0

            if datalen != len(func.EXT_argnames):
                responses.append({
                    'type': 'exception',
                    'tid': tid,
                    'message': 'invalid arguments',
                    'where': 'Expected %d, got %d' % ( len(func.EXT_argnames), len(data) )
                })
                continue

            try:
                if data:
                    result = func(request, *data)
                else:
                    result = func(request)

            except Exception as err:
                errinfo = {
                    'type': 'exception',
                    "tid": tid,
                }
                if settings.DEBUG:
                    traceback.print_exc(file=stderr)
                    errinfo['message'] = str(err)
                    errinfo['where'] = traceback.format_exc()
                else:
                    errinfo['message'] = str(err)
                    errinfo['where'] = ''
                responses.append(errinfo)

            else:
                if isinstance(result, HttpResponse) and result.status_code != 200:
                    try:
                        content = result.content.decode('UTF-8')
                    except AttributeError:
                        content = result.content

                    if (
                        not content and result.status_code == 302
                        and result._headers.get(
                            'location', ('', '!')
                        )[1].startswith(settings.LOGIN_URL)
                    ):
                        content = 'Login Required / Session Expired'

                    responses.append({
                        'type': 'exception',
                        'tid': tid,
                        'message': content,
                        'where': '',
                    })
                else:
                    if isinstance(result, json_str):
                        _ = '<<JSON!STR:{}>>'.format(len(responses))
                        replace_json_strs.append((_, result))
                        result = _

                    responses.append({
                        "type": rtype,
                        "tid": tid,
                        "action": cls,
                        "method": methname,
                        "result": result
                    })

        if len(responses) == 1:
            responses = responses[0]

        resp = json.dumps(responses, cls=DjangoJSONEncoder)

        for rep, jstr in replace_json_strs:
            resp = resp.replace('"{}"'.format(rep), jstr, 1)

        return HttpResponse(resp, content_type="application/json")

    def process_form_request(self, request, reqinfo):
        """ Router for POST requests that submit form data and/or file uploads. """
        cls, methname, rtype, tid = (
            reqinfo['action'],
            reqinfo['method'],
            reqinfo['type'],
            reqinfo['tid'],
        )

        replace_json_str = None

        if cls not in self.classes:
            response = {
                'type': 'exception',
                'message': 'no such action',
                'where': cls,
                "tid": tid,
            }

        elif methname not in self.classes[cls]:
            response = {
                'type': 'exception',
                'message': 'no such method',
                'where': methname,
                "tid": tid,
            }

        else:
            func = self.classes[cls][methname]
            try:
                result = func(request)

            except Exception as err:
                errinfo = {
                    'type': 'exception',
                    "tid": tid,
                }
                if settings.DEBUG:
                    traceback.print_exc(file=stderr)
                    errinfo['message'] = str(err)
                    errinfo['where'] = traceback.format_exc()
                else:
                    errinfo['message'] = str(err)
                    errinfo['where'] = ''
                response = errinfo

            else:
                if isinstance(result, json_str):
                    replace_json_str = result
                    result = '<<JSON!STR>>'

                response = {
                    "type": rtype,
                    "tid": tid,
                    "action": cls,
                    "method": methname,
                    "result": result
                }

        if reqinfo['upload'] == "true":
            return HttpResponse(
                "<html><body><textarea>%s</textarea></body></html>" % json.dumps(response, cls=DjangoJSONEncoder),
                content_type="application/json"
            )

        resp = json.dumps(responses, cls=DjangoJSONEncoder)

        if replace_json_str:
            resp = resp.replace('"<<JSON!STR>>"', replace_json_str, 1)

        return HttpResponse(resp, content_type="application/json")

    @property
    def urls(self):
        """ Return the URL patterns. """
        return [
            url(r'api.json$', self.get_api_plain, name='api.json'),
            url(r'api.js$', self.get_api, name='api.js'),
            url(r'router/?', self.request, name='router'),
        ]
