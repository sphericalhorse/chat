from django.contrib.auth.signals import user_logged_out
import pika
from pika.exceptions import ConnectionClosed
from django.conf import settings
import json


class ChatMiddleware(object):

	def __init__(self):
		channel = self._get_channel()
		channel.queue_declare(queue=settings.CHAT_AMQP_QUEUE)

	def _get_channel(self, force=False):
		if not hasattr(self, '_connection') or not self._connection.is_open or force:
			self._connection = pika.BlockingConnection(pika.ConnectionParameters(host='localhost'))
			self._channel = self._connection.channel()
		return self._channel

	def _publish(self, message, force_new_channel=False):
		try:
			channel = self._get_channel(force=force_new_channel)
			channel.basic_publish(
				exchange='',
				routing_key=settings.CHAT_AMQP_QUEUE,
				body=message,
			)
		except ConnectionClosed:
			# Tries to reopen channel and publish again.
			# If channel already was reopened, than it not helpes and we should
			# pass ConnectionClosed exception.
			if not force_new_channel:
				self._publish(message, force_new_channel=True)
			else:
				raise ConnectionClosed()

	def process_request(self, request):
		self.old_session_key = request.COOKIES.get(settings.SESSION_COOKIE_NAME, None)
		self.was_anonymous = request.user.is_anonymous()

		return None

	def process_response(self, request, response):
		try:
			accessed = request.session.accessed
			modified = request.session.modified
			empty = request.session.is_empty()
		except AttributeError:
			pass
		else:
			# First check if we need to delete this cookie.
			# The session should be deleted only if the session is entirely empty
			if settings.SESSION_COOKIE_NAME in request.COOKIES and empty:
				self._publish(json.dumps({
					'type': 'session_delete',
					'session_key': self.old_session_key,
				}))
			elif (
				modified and not empty
				and response.status_code != 500
				and self.old_session_key != request.session.session_key
				and not self.was_anonymous
			):
				self._publish(json.dumps({
					'type': 'session_key_update',
					'old_session_key': self.old_session_key,
					'new_session_key': request.session.session_key,
				}))


		return response
