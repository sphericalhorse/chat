# http://djangosnippets.org/snippets/2296/

from django.conf import settings

def settings_context(request):
    return {
        'settings': settings.__dict__.get('_wrapped').__dict__.copy()
    }
