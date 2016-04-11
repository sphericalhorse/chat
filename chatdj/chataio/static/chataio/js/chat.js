$(function() {

	var chatApp = {
		conf: window.chatConf
		, reconnectStep: 1
		, views: {}
		, mainView: undefined
		, closeOpenView: undefined

		, collections: {}
		
		, helpers: {}
		, client: undefined
	}

	chatApp.conf = window.chatConf

	chatApp.helpers.Client = function() {}
	_.extend(chatApp.helpers.Client.prototype, Backbone.Events)

	chatApp.helpers.Client.prototype.open = function() {
		var self = this

		self.socket = new WebSocket(chatApp.conf.socket)
		self.socket.addEventListener('open', function(event) {
			self.trigger('open')
		})

		self.socket.addEventListener('close', function(event) {
			if(event.wasClean) {
				self.trigger('close')
			} else {
				self.trigger('error')
			}
		})

		// this event is catched on close listener
		// self.socket.addEventListener('error', function(event) {
		// 	self.trigger('error')
		// })


		self.socket.addEventListener('message', function(event) {
			var message = JSON.parse(event.data)
			self.trigger('message message:' + (message.type ? message.type : 'notype'), message)
		})
	}
	chatApp.helpers.Client.prototype.close = function() {
		var self = this
		self.socket.close()
	}
	chatApp.helpers.Client.prototype.isClosed = function() {
		var self = this
		return self.socket.readyState == WebSocket.CLOSED
	}
	chatApp.helpers.Client.prototype.get_user_list = function() {
		var self = this

		self.socket.send(JSON.stringify({ 'type': 'get_user_list', 'wrap': true }))
	}

	chatApp.helpers.Client.prototype.get_online_user_list = function() {
		var self = this

		self.socket.send(JSON.stringify({ 'type': 'get_online_user_list', 'wrap': true }))
	}

	chatApp.helpers.Client.prototype.message = function(to, message) {
		var self = this

		self.socket.send(JSON.stringify({type: 'message', to: to, message: message, time: new Date().getTime()}))
	}


	chatApp.collections.UserCollection = Backbone.Collection.extend({
		idAttribute: 'id'
	})

	chatApp.collections.MessageCollection = Backbone.Collection.extend({
	})


	chatApp.views.CloseOpenView = Backbone.View.extend({
		tagName: 'div'
		, className: 'chat-openclose'
		, events: {
			'click': 'changeState'
		}
		, initialize: function() {
			var self = this
			
			self.opened = false

			self.on('open', function() {
				self.opened = true
				self.render()
			})

			self.on('close', function() {
				self.opened = false
				self.render()
			})

			self.render()
		}
		, render: function() {
			this.$el.text((this.opened ? 'Close' : 'Open' ) + ' chat')
		}
		, changeState: function() {
			var self = this
			self.trigger(!self.opened ? 'open' : 'close')
		}
	})


	chatApp.views.MsgBoxView = Backbone.View.extend({
		tagName: 'div'
		, className: 'chat-msgbox'
		, events: {
			'submit form': 'msgSend'
			, 'keypress textarea': 'handleEnter'
		}
		, $form: undefined
		, template: _.template($('#tplMsgBox').html())
		, templateMsg: _.template($('#tplMsgBoxMsg').html())
		, initialize: function(options) {
			var self = this

			self.companionModel = options.companionModel

			self.render()

			self.$form = self.$el.find('form')
			self.$messages = this.$el.find('.chat-msgbox-messages')
			self.$textarea = this.$el.find('textarea')



			var handleMessage = function(message) {
				if(message.get('from') == self.companionModel.id) {
					self.$messages.append(self.templateMsg({
						message: message.get('message'),
						user: chatApp.usersCollection.get(message.get('from')).get('name'),
						className: 'chat-msgbox-message-from'
					}))
				} else if (message.get('to') == self.companionModel.id) {
					self.$messages.append(self.templateMsg({
						message: message.get('message'),
						user: false,
						className: 'chat-msgbox-message-to'
					}))
				}

				self.scrollBotttom()
			}
			chatApp.messageCollection.on('add', handleMessage)
			chatApp.messageCollection.each(handleMessage)


		}
		, scrollBotttom: function() {
			var self = this

			self.$messages.scrollTop(self.$messages.prop('scrollHeight'))
		}
		, render: function() {
			var self = this

			self.$el.html(self.template({name: self.companionModel.get('name')}))
		}
		, handleEnter: function(event) {
			if(event.which == 13 && !event.shiftKey && !event.ctrlKey) {
				this.$form.trigger('submit')
				return false
			}
		}
		, msgSend: function() {
			var self = this

			var message = self.$textarea.val().trim()

			if(message) {
				chatApp.client.message(self.companionModel.id, message)
			}

			self.$form.get(0).reset()
			
			return false
		}
	})

	chatApp.views.UserView = Backbone.View.extend({
		tagName: 'div'
		, className: 'chat-usersbox-user'
		, events: {
			'click': 'openChat'
		}
		, initialize: function() {
			var self = this

			this.render()
		}
		, render: function() {
			var self = this

			self.$el.toggleClass('chat-usersbox-user-online', self.model.get('status') == 'online')
			
			self.$el.text(self.model.get('name'))
		}
		, openChat: function() {
			var self = this

			self.$el.siblings().removeClass('chat-usersbox-user-open')
			self.$el.addClass('chat-usersbox-user-open')


			if(chatApp.msgBoxView) {
				chatApp.msgBoxView.remove()
				chatApp.msgBoxView = undefined
			}

			chatApp.msgBoxView = new chatApp.views.MsgBoxView({companionModel: self.model})
			
			chatApp.mainView.$el.append(chatApp.msgBoxView.$el)

			chatApp.msgBoxView.scrollBotttom()
		}
	})

	chatApp.views.UsersView = Backbone.View.extend({
		tagName: 'div'
		, events: {
			'click .js-get-user-list': 'get_user_list'
			, 'click .js-get-online-user-list': 'get_online_user_list'
		}
		, className: 'chat-usersbox'
		, template: _.template($('#tplUserBox').html())
		, $users: undefined
		, initialize: function() {
			var self = this


			self.render()

			self.$users = self.$el.find('.chat-usersbox-users')

			self.collection.on('add', function(userModel) {
				// dont show self
				if(userModel.id == chatApp.conf.userId) {return}

				userModel.userView = new chatApp.views.UserView({model: userModel})
				self.$users.append(userModel.userView.$el)
			})

			self.collection.on('change', function(userModel) {
				// dont show self
				if(userModel.id == chatApp.conf.userId) {return}

				userModel.userView.render()
			})
		}
		, render: function() {
			var self = this
			
			self.$el.html(self.template())
		}
		, get_user_list: function() {
			chatApp.client.get_user_list()
		}
		, get_online_user_list: function() {
			chatApp.client.get_online_user_list()
		}
	})

	chatApp.views.MainView = Backbone.View.extend({
		el: '#chat'
		, initialize: function() {
			var self = this

			chatApp.closeOpenView = new chatApp.views.CloseOpenView()
			

			chatApp.closeOpenView.on('open', function() {

				chatApp.client = new chatApp.helpers.Client()

				chatApp.client.on('error', function() {
					var reconnectTime = Math.floor(Math.exp(chatApp.reconnectStep))

					$.notify('Chat conntcion error.\nAuto reconnect in ' + reconnectTime + ' seconds.', {autoHideDelay: (reconnectTime + 1) * 1000})
					chatApp.closeOpenView.trigger('close')

					setTimeout(function() {
						// prevent from autoreconect if user already reconnected
						// by clicking 'Open chat' button
						if(chatApp.client.isClosed()) {

							++chatApp.reconnectStep;
							chatApp.closeOpenView.trigger('open')
						
						}
					}, reconnectTime * 1000)
				})
				
				chatApp.client.open()

				chatApp.client.on('open', function() {
					chatApp.reconnectStep = 1
					chatApp.usersCollection = new chatApp.collections.UserCollection()
					chatApp.messageCollection = new chatApp.collections.MessageCollection()

					chatApp.usersView = new chatApp.views.UsersView({collection: chatApp.usersCollection})
					self.$el.append(chatApp.usersView.$el)

					chatApp.client.on('message:get_user_list', function(message) {
						chatApp.usersCollection.set(message.data)
					})
					chatApp.client.on('message:get_online_user_list', function(message) {
						var usersToHandle = message.data

						chatApp.usersCollection.each(function(userModel) {
							var userOnlineIndex = _.findIndex(usersToHandle, {'id': userModel.id})
							if(userOnlineIndex != -1) {
								userModel.set({'status': 'online'})
								usersToHandle.splice(userOnlineIndex, 1)
							} else {
								userModel.set({'status': 'offline'})
							}
						})

						// if get_online_user_list takes users that not be loaded before
						chatApp.usersCollection.add(usersToHandle)
					})

					chatApp.client.on('message:status', function(message) {
						var user = chatApp.usersCollection.get(message.id)
						user.set({'status': message.status})
					})

					chatApp.client.on('message:message', function(message) {
						chatApp.messageCollection.add(message)
					})

					chatApp.client.on('message:error', function(message) {
						$.notify(message.message)
					})

					chatApp.client.on('message:logout', function(message) {
						$.notify(message.message)
					})

					chatApp.client.on('close', function() {
						chatApp.closeOpenView.trigger('close')
					})

					chatApp.client.get_user_list()
				})
			})

			chatApp.closeOpenView.on('close', function() {
				if(chatApp.usersView) {
					chatApp.usersView.remove()
					chatApp.usersView = undefined
				}

				if(chatApp.msgBoxView) {
					chatApp.msgBoxView.remove()
					chatApp.msgBoxView = undefined
				}
				if(! chatApp.client.isClosed()) {
					chatApp.client.close()
				}
			})


			self.render()
		}
		, render: function() {
			this.$el.html(chatApp.closeOpenView.$el)
		}
	})


	chatApp.mainView = new chatApp.views.MainView()


	window.chatApp = chatApp
})