from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User


class LoginAsAuthBackend(ModelBackend):
	def authenticate(self, username=None, from_login_as_view = False):
		if not from_login_as_view:
			return None
		try:
			user = User.objects.get(username=username, groups__name = 'login_as')

			return user

		except User.DoesNotExist:
			return None

	def get_user(self, user_id):
		try:
			return User.objects.get(pk=user_id)
		except User.DoesNotExist:
			return None