djextdirect
===========

Fork of https://bitbucket.org/Svedrin/djextdirect

Provider for Ext.Direct. This class handles building API information and routing requests to the appropriate functions, and serializing their response and exceptions - if any.

Instantiation:

```python
EXT_JS_PROVIDER = Provider([name="Ext.app.REMOTING_API", autoadd=True])
```

If `autoadd` is True, the api.js will include a line like such:

```javascript
Ext.Direct.addProvider(Ext.app.REMOTING_API);
```

After instantiating the Provider, register functions to it like so:

```python
@EXT_JS_PROVIDER.register_method("myclass")
def myview( request, possibly, some, other, arguments ):
    """does something with all those args and returns something """
    return 13.37
```
Note that those views MUST NOT return an `HttpResponse` but simply the plain result, as the Provider will build a response from whatever your view returns!

To be able to access the Provider, include its URLs in an arbitrary URL pattern, like so:

```python
from views import EXT_JS_PROVIDER # import our provider instance
urlpatterns = patterns(
    # other patterns go here
    (r'api/', include(EXT_DIRECT_PROVIDER.urls)),
)
```

This way, the Provider will define the URLs "api/api.js" and "api/router".

If you then access the "api/api.js" URL, you will get a response such as::

```javascript
Ext.app.REMOTING_API = { // Ext.app.REMOTING_API is from Provider.name
    "url": "/api/router",
    "type": "remoting",
    "actions": {"myclass": [{"name": "myview", "len": 4}]}
}
```
You can then use this code in ExtJS to define the Provider there.
