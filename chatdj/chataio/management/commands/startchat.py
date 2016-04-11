from django.core.management.base import BaseCommand

from importlib import import_module
from datetime import datetime

import json
from jsonschema import validate as json_validate
from jsonschema.exceptions import ValidationError

import asyncio, aioamqp, aiohttp
from aiohttp import web
from aiohttp.errors import WSClientDisconnectedError

from django.conf import settings
from django.contrib.auth import get_user as django_get_user
from django.contrib.auth.models import User
from django.db.models import Q
from chataio.models import Message

class Command(BaseCommand):
	def add_arguments(self, parser):
		parser.add_argument(
			"-H", "--hostname",
			help="TCP/IP hostname to serve on (default: %(default)r)",
			default="localhost",
		)
		parser.add_argument(
			"-P", "--port",
			help="TCP/IP port to serve on (default: %(default)r)",
			type=int,
			default="8080",
		)

	def handle(self, **options):
		hostname = options.get('hostname')
		port = options.get('port')
		amqp_queue = getattr(settings, 'CHAT_AMQP_QUEUE', 'chat')

		loop = asyncio.get_event_loop()
		server = ServerApp(loop)
		loop.run_until_complete(server.init_web(hostname, port))
		loop.run_until_complete(server.init_amqp(amqp_queue))

		loop.run_forever()

class DjangoAdapter(object):
	session_engine = import_module(settings.SESSION_ENGINE)
	session_store = session_engine.SessionStore

	@classmethod
	def get_user(cls, session_key):
		django_session = cls.session_store(session_key).load()

		class DummyRequest(object):
			def __init__(self, session):
				self.session = session

		user = django_get_user(DummyRequest(django_session))
		return user

	class NotAuthorized(Exception):
		pass


class Connection(object):
	def __init__(self, session_key, user):
		self.session_key = session_key
		self.user = user
		self.user_id = user.id
		self.sockets = []
	
class Connections(object):
	_by_session_key = {}
	_by_user_id = {}

	def __init__(self, server_app):
		self._server_app = server_app

	def get_all(self):
		return self._by_session_key.values()

	def get_all_sockets(self):
		return sum([conn.sockets for conn in self.get_all()], [])

	# NOTE: this method chane both self._by_session_key and self._by_user_id
	def get_by_session_key(self, session_key):
		# return if exists
		if session_key in self._by_session_key:
			return self._by_session_key[session_key]
		
		# not authorised users not allowed to use chat
		user = DjangoAdapter.get_user(session_key)
		if user.is_anonymous():
			raise DjangoAdapter.NotAuthorized

		# create connection
		connection = Connection(session_key, user)

		# add connection to self._by_session_key
		self._by_session_key[session_key] = connection

		# check if user was not connected
		if connection.user_id not in self._by_user_id:
			self._by_user_id[connection.user_id] = []

			# notify all users that new user came online
			self._server_app.messages.respond_online(user=connection.user)

		# add connection to self._by_user_id
		self._by_user_id[connection.user_id].append(connection)

		return connection

	def sockets_by_session_key(self, session_key):
		return self.get_by_session_key(session_key).sockets

	def get_by_user_id(self, user_id):
		return self._by_user_id.get(user_id, [])

	def sockets_by_user_id(self, user_id):
		return sum([conn.sockets for conn in self.get_by_user_id(user_id)], [])

	# NOTE: this method chane both self._by_session_key and self._by_user_id
	def add_socket(self, connection, socket):
		connection.sockets.append(socket)
	
	# NOTE: this method chane both self._by_session_key and self._by_user_id
	def del_socket(self, connection, socket):
		# When user click on Logout link and chat is opened, socket deletes from
		# ServerApp.websocket_handler. Then Django pass message here, and system
		# tries to delete already deletes socket by Connections.disconnect.
		if not socket in connection.sockets:
			return
		
		connection.sockets.remove(socket)

		# remove connection if no sockets left
		if not connection.sockets:
			
			del self._by_session_key[connection.session_key]
			self._by_user_id[connection.user_id].remove(connection)

			# remove user if no users conntcions left
			if not self._by_user_id[connection.user_id]:
				del self._by_user_id[connection.user_id]
				# notify all that user came offline
				self._server_app.messages.respond_offline(user=connection.user)

	# NOTE: this method chane both self._by_session_key and self._by_user_id
	@asyncio.coroutine
	def handle_logout(self, session_key):
		# Protect from repeated messages
		if not session_key in self._by_session_key:
			return

		conn = self._by_session_key[session_key]

		self._server_app.messages.respond_logout(session_key=session_key)

		# close and remove all usres sockets
		while conn.sockets:
			socket = conn.sockets[0]
			yield from socket.close()
			self.del_socket(conn, socket)


	# NOTE: this method chane both self._by_session_key and self._by_user_id
	def update_session_key(self, old_session_key, new_session_key):
		# Protect from repeated messages
		if not old_session_key in self._by_session_key:
			return

		conn = self._by_session_key[old_session_key]
		conn.session_key = new_session_key
		self._by_session_key[new_session_key] = conn
		
		del self._by_session_key[old_session_key]

	def is_user_online(self, user_id):
		return user_id in self._by_user_id

	def get_online_users(self):
		res = []
		for user_id in self._by_user_id:
			res.append(self._by_user_id[user_id][0].user)
		return res


class Messages(object):

	def __init__(self, server_app):
		self._server_app = server_app

	class RequestDataError(Exception):
		pass
	class RequestTypeError(Exception):
		pass
	class RequestSchemaError(Exception):
		pass
	class MessageHandlingError(Exception):
		pass

	def _schema(message_schema):
		def decorate(message_handler):
			def decorator(self, message, *args, **kwargs):
				try:
					json_validate(message, message_schema)
				except ValidationError:
					raise Messages.RequestSchemaError
				return message_handler(self, message, *args, **kwargs)
			return decorator
		return decorate

	def handle_request(self, request_data, *args, **kwargs):
		try:
			request = json.loads(request_data)
		except ValueError:
			raise Messages.RequestDataError

		handler_type = request['type']

		try:
			handler = getattr(self, 'request_' + handler_type)
		except AttributeError:
			raise Messages.RequestTypeError

		return handler(request, *args, **kwargs)

	@_schema({
		'type': 'object',
		'properties': {
			'type': {'type': 'string', 'enum': ['message']},
			'message': {'type': 'string'},
			'to': {'type': 'number', 'minimum': 1},
			'time': {'type': 'number', 'minimum': 1}
		},
		'required': ['type', 'message', 'to', 'time'],
		'additionalProperties': False,
	})
	def request_message(self, request, **kwargs):
		user = kwargs['user']

		try:
			reciever_user = User.objects.get(pk=int(request['to']))
		except User.DoesNotExist:
			raise Messages.MessageHandlingError
		
		message = Message(
			sender = user,
			receiver = reciever_user,
			body = request['message'],
			datetime = datetime.fromtimestamp(request['time'] / 1000)
		)
		message.save()

		resp = {
			'type': 'message',
			'message': request['message'],
			'from': user.id
		}

		for socket in self._server_app.connections.sockets_by_user_id(reciever_user.id):
			socket.send_str(json.dumps(resp))

		resp = {
			'type': 'message',
			'message': request['message'],
			'to': reciever_user.id
		}
		for socket in self._server_app.connections.sockets_by_user_id(user.id):
			socket.send_str(json.dumps(resp))

	@_schema({
		'type': 'object',
		'properties': {
			'type': {'type': 'string', 'enum': ['get_user_list']},
			'wrap': {'type': 'boolean'},
		},
		'required': ['type'],
		'additionalProperties': False,
	})
	def request_get_user_list(self, request, **kwargs):
		socket = kwargs['socket']

		wrap = request.get('wrap', False)

		users_queryset = User.objects.values('id', 'username')

		users = [
			{
				'id': user['id'],
				'name': user['username'],
				'status': self._server_app.connections.is_user_online(user['id']) and 'online' or 'offline',
				'avatar': '',
			}
			for user
			in users_queryset
		]
		
		resp = wrap and {'type': 'get_user_list', 'data': users} or users

		resp_json = json.dumps((resp))

		socket.send_str(resp_json)


	@_schema({
		'type': 'object',
		'properties': {
			'type': {'type': 'string', 'enum': ['get_online_user_list']},
			'wrap': {'type': 'boolean'},
		},
		'required': ['type'],
		'additionalProperties': False,
	})
	def request_get_online_user_list(self, request, **kwargs):
		socket = kwargs['socket']

		wrap = request.get('wrap', False)

		users = [
			{'id': user.id, 'name': user.username, 'status': 'online', 'avatar': ''}
			for user
			in self._server_app.connections.get_online_users()
		]


		resp = wrap and {'type': 'get_online_user_list', 'data': users} or users

		resp_json = json.dumps((resp))

		socket.send_str(resp_json)

	def respond_wrong_request(self, **kwargs):
		socket = kwargs['socket']

		resp = {
			'type': 'error',
			'message': 'Wrong request.',
		}

		socket.send_str(json.dumps(resp))

	def respond_messages_recieved(self, **kwargs):
		socket = kwargs['socket']
		user = kwargs['user']


		for msg in Message.objects.filter(Q(sender_id = user.id)| Q(receiver_id = user.id)):
			resp = {
				'type': 'message',
				'message': msg.body,
			}
			if msg.sender_id == user.id:
				resp['to'] = msg.receiver_id
			else:
				resp['from'] = msg.sender_id
			socket.send_str(json.dumps(resp))


	def respond_not_authorized(self, **kwargs):
		socket = kwargs['socket']

		resp = {
			'type': 'error',
			'message': 'Not authorized.',
		}

		socket.send_str(json.dumps(resp))

	def respond_online(self, **kwargs):
		user = kwargs['user']
		
		resp = {
			'type': 'status',
			'id': user.id,
			'status': 'online',
		}

		resp_json = json.dumps(resp)

		for socket in self._server_app.connections.get_all_sockets():
			socket.send_str(resp_json)
	

	def respond_offline(self, **kwargs):
		user = kwargs['user']
		
		resp = {
			'type': 'status',
			'id': user.id,
			'status': 'offline',
		}

		resp_json = json.dumps(resp)

		for socket in self._server_app.connections.get_all_sockets():
			socket.send_str(resp_json)


	def respond_logout(self, **kwargs):
		session_key = kwargs['session_key']

		resp = {
			'type': 'logout',
			'message': 'logged out',
		}

		resp_json = json.dumps(resp)

		for socket in self._server_app.connections.sockets_by_session_key(session_key):
			socket.send_str(resp_json)

class ServerApp(object):
	def __init__(self, loop):
		self.connections = Connections(server_app=self)
		self.messages = Messages(server_app=self)
		self.loop = loop

	@asyncio.coroutine
	def amqp_handle(self, channel, body, envelope, properties):
		message = json.loads(body.decode('utf-8'))

		if message['type'] == 'session_delete':
			yield from self.connections.handle_logout(message['session_key'])
		elif message['type'] == 'session_key_update':
			self.connections.update_session_key(message['old_session_key'], message['new_session_key'])

	@asyncio.coroutine
	def init_amqp(self, queue_name):
		transport, protocol = yield from aioamqp.connect()
		channel = yield from protocol.channel()

		yield from channel.queue_declare(queue_name=queue_name)

		yield from channel.basic_consume(self.amqp_handle, queue_name=queue_name, no_ack=True)

	@asyncio.coroutine
	def init_web(self, host, port):
		app = web.Application()
		app.router.add_route("GET", "/", self.websocket_handler)
		srv = yield from self.loop.create_server(app.make_handler(), host, port)
		return srv

	@asyncio.coroutine
	def websocket_handler(self, request):
		session_key = request.cookies.get(settings.SESSION_COOKIE_NAME, None)

		ws = web.WebSocketResponse()
		yield from ws.prepare(request)

		try:
			connection = self.connections.get_by_session_key(session_key)
		except DjangoAdapter.NotAuthorized:
			self.messages.respond_not_authorized(socket=ws)
			yield from ws.close()

			return ws


		self.connections.add_socket(connection, ws)

		
		self.messages.respond_messages_recieved(user=connection.user, socket=ws)
		
		while not ws.closed:
			try:
				ws_request = yield from ws.receive()
			except WSClientDisconnectedError:
				break

			if ws_request.tp == aiohttp.MsgType.text:
				try:
					self.messages.handle_request(ws_request.data, user=connection.user, socket=ws)
				except (
					Messages.RequestDataError,
					Messages.RequestTypeError,
					Messages.RequestSchemaError,
					Messages.MessageHandlingError,
				):
					self.messages.respond_wrong_request(user=connection.user, socket=ws)

			elif ws_request.tp == aiohttp.MsgType.error or ws_request.tp == aiohttp.MsgType.close:
				break


		self.connections.del_socket(connection, ws)

		return ws