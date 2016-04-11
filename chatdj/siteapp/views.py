from django.shortcuts import render, redirect
from django.core.urlresolvers import reverse
from django.http import HttpResponseBadRequest

from django.contrib.auth.views import login as view_login, logout as view_logout
from django.contrib.auth import login as auth_login, authenticate as auth_authenticate
from siteapp.forms import CustomAuthenticationForm, CustomUserCreationForm
from django.contrib.auth.models import Group


def index(request):
	group = Group.objects.get(name='login_as')
	users_to_log_in = group.user_set.all()

	return render(request, 'index.html', {'users_to_log_in': users_to_log_in})

def login(request, *args, **kwargs):
	if request.user.is_authenticated():
		next_url = request.POST.get('next', request.GET.get('next'))
		return redirect(next_url or reverse('index'))

	kwargs.update({
		'template_name': 'login.html',
		'authentication_form': CustomAuthenticationForm,
	})

	return view_login(request, *args, **kwargs)

def logout(request, *args, **kwargs):
	if request.user.is_anonymous():
		next_url = request.POST.get('next', request.GET.get('next'))
		return redirect(next_url or reverse('index'))

	kwargs.update({
		'template_name': 'logged_out.html'
	})

	return view_logout(request, *args, **kwargs)


def registration(request):
	if request.method == 'POST':
		form = CustomUserCreationForm(request.POST)
		if form.is_valid():
			new_user = form.save()

			user = auth_authenticate(username=form.cleaned_data['username'], password=form.cleaned_data['password1'])
			auth_login(request, user)

			next_url = request.POST.get('next', request.GET.get('next'))
			return redirect(next_url or reverse('index'))
	else:
		form = CustomUserCreationForm()
	
	return render(request, 'registration.html', {
		'form': form,
	})


def login_as(request, username):
	if request.user.is_authenticated():
		return HttpResponseBadRequest("Error 400 :(\nNo-no-no!")

	user = auth_authenticate(username=username, from_login_as_view = True)

	if not user:
		return HttpResponseBadRequest("Error 400 ;(\nNo-no-no!")

	auth_login(request, user)

	return redirect(reverse('index'))