make:
	lessc chatdj/siteapp/static/css/style.less chatdj/siteapp/static/css/style.css
	cd chatdj && echo yes | ./manage.py collectstatic
