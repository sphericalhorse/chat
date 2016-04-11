Hi!

This repo contains simple online chat, that worsk over WebSokets protocol.

It based on Django (for auth system and generating HTML), and on aiohttp to handle WebSocket connections.

Also it uses RabbitMQ to communicate between Django and aiohttp application.


Django's project located in `./chatdj/` directory.
There are `nginx.conf` and `uwsgi.ini` to set up Django over nginx.

aiohttp application made as Django custom command and located in `./chatdj/chataio/management/commands/startchat.py`. So it should be started as `./manage.py startchat`.
There are `./chataio/nginx.conf` and `./chataio/supervisor.conf` to set up aiohttp application over nginx.
