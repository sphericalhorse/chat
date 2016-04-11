from django.db import models
from django.contrib.auth.models import User

class Message(models.Model):
	sender = models.ForeignKey(User, related_name='messages_sended')
	receiver = models.ForeignKey(User, related_name='messages_recieved')
	datetime = models.DateTimeField(editable = False)
	body = models.TextField()

	class Meta:
		ordering = ['-id']