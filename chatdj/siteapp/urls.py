from django.conf.urls import patterns, url

urlpatterns = patterns('siteapp.views',
	url(r'^login/$', 'login', name='login'),
	url(r'^login_as/(?P<username>[\w.@+-]+)/$', 'login_as', name='login_as'),
	url(r'^logout/$', 'logout', name='logout'),
	url(r'^registration/$', 'registration', name='registration'),
	url(r'^$', 'index', name='index'),
)