from django.utils.translation import ugettext, ugettext_lazy as _
from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

class CustomAuthenticationForm(AuthenticationForm):
	username = forms.CharField(max_length=254, widget=forms.TextInput(attrs={'class': 'form-control'}))
	password = forms.CharField(label=_("Password"), widget=forms.PasswordInput(attrs={'class': 'form-control'}))

class CustomUserCreationForm(UserCreationForm):

	def __init__(self, *args, **kwargs):
		res = super(CustomUserCreationForm, self).__init__(*args, **kwargs)

		self.fields['username'].widget.attrs['class'] = getattr(self.fields['username'].widget.attrs, 'class', '') + ' form-control'
		self.fields['password1'].widget.attrs['class'] = getattr(self.fields['password1'].widget.attrs, 'class', '') + ' form-control'
		self.fields['password2'].widget.attrs['class'] = getattr(self.fields['password2'].widget.attrs, 'class', '') + ' form-control'

		return res