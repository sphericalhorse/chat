from django.contrib import admin

from chataio import models

class MessageAdmin(admin.ModelAdmin):
	list_display = ('id', 'datetime', 'sender', 'receiver', 'body')

admin.site.register(models.Message, MessageAdmin)