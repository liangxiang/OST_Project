import webapp2
import jinja2
import os
import urllib
import re
import cgi
import time

from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api import users
from google.appengine.ext import blobstore
from google.appengine.ext.webapp import blobstore_handlers


JINJA_ENVIRONMENT = jinja2.Environment(
	loader=jinja2.FileSystemLoader(os.path.dirname(__file__)),
	extensions=['jinja2.ext.autoescape'],
	autoescape=True)

# KEY='posts'

HOST_PATH='http://lx350-final\.appspot\.com'

def render_str(template, **params):
	t = JINJA_ENVIRONMENT.get_template(template)
	return t.render(params)

def is_owner(user):
	if users.User(user) != users.get_current_user():
		return False;
	else:
		return True;

class Mainpage(webapp2.RequestHandler):
	def get(self):        
		self.query = {}
		self.user = users.get_current_user()

		self.users = users
		self.posts = Question.all().order('-create_time')
		for post in self.posts:
#			post.render_text = post.body[:500].replace('\n', '<br>') + ' ... (more) ...'
			post.render()
			post.put()
		time.sleep(0.1)

		self.response.write(render_str('index.html', p = self))


		'''
		self.response.write(render_str('header_template.html', p = self))
		fetch = self.request.get('fetch')
		if not fetch:
			fetch = 0
		fetch = int(fetch)
		self.query['fetch'] = int(fetch)

		posts = Question.all().order('-create_time')

		for post in posts:
			self.response.write(post.render())
		if self.user:
			self.response.write(render_str('blog_control.html', p = self))
		'''

class ViewQuestion(webapp2.RequestHandler):
	def get(self, question_id):
		self.user = users.get_current_user()
		self.users = users
		
		self.response.write(render_str('header_template.html', p = self))

		question=Question.get_by_id(int(question_id))
		self.response.write(question.render(True, question_id))

		answers=db.GqlQuery('select * from Answer where question_id = :1 order by answervote desc', question_id)
		for answer in answers:
			self.response.write(answer.answervote)
			self.response.write(answer.render())
		'''
		self.parent=question_id
		if self.user:
			self.response.write(render_str('question_control.html', p = self))
		'''


class Question(db.Model):
	user = db.UserProperty()
	body = db.TextProperty()
	tags = db.StringListProperty()
	create_time = db.DateTimeProperty(auto_now_add = True)
	last_modified = db.DateTimeProperty(auto_now = True)
	has_modified = db.BooleanProperty()
	questionvote = db.IntegerProperty()
	render_text = db.TextProperty()
	is_editable = db.BooleanProperty()

	def render(self, render_full_text=False, question_id=None):
		if len(self.body) > 500 and not render_full_text:
			self.render_text = self.body[:500].replace('\n', '<br>') + ' ... (more) ...'
		else:
			self.render_text = self.body.replace('\n', '<br>')

		
		http = r'(https?://\w[^ \t<]*)'
		img_pattern = r'\.(png|jpg|gif)$'
		img = re.compile(img_pattern)


		local_img = re.compile(r'(localhost:\d+/pic/[^/ ]+)|({0}/pic/[^/ ]+)'.format(HOST_PATH))
		links = re.findall(http, self.render_text)

		for link in links:
		    if img.search(link) or local_img.search(link):
		        self.render_text = re.sub(r'({0})'.format(link), r'<a href="\1"><img src="\1" alt="Image"></a>', self.render_text)
		    else:
		        self.render_text = re.sub(r'({0})'.format(link), r'<a href="\1"> \1 </a>', self.render_text)

		if self.user == users.get_current_user():
			self.is_editable = True
		else:
			self.is_editable = False

		if not render_full_text:
			self.show_permalink = True

#		return render_str('blog_post_template.html', p = self)

	def refresh(self, question_id):
		votes = db.GqlQuery('select * from QuestionVote where question_id = :1', question_id)
		questionvote = 0
		for vote in votes:
			questionvote = questionvote+vote.vote
		self.questionvote=questionvote


class QuestionEdit(webapp2.RequestHandler):    
	def get(self, question_id):        
		user = users.get_current_user()
		question = Question.get_by_id(int(question_id))
		self.response.write(self.render(question))

	def render(self, p=None):
		if p:
			p.body_str = p.body
		else:
			class p: pass
			p.body_str = ''
		p.user = users.get_current_user()
		p.users = users
		return render_str('createquestion.html', p=p)

class NewQuestion(QuestionEdit):
	def get(self):
		self.response.write(self.render())


class QuestionEntry(webapp2.RequestHandler):
	def post(self, question_id=None):
		if not question_id:
			post = Question()
			post.user = users.get_current_user()
		else:
			# TODO Check if the blog post is oiwned by the current user
			post = Question.get_by_id(int(question_id))
			post.has_modified = True

		post.body = self.request.get('body')
		post.tags = self.request.get('tags').split()
		post.questionvote = 0

		key = post.put()

		# memcache.delete(KEY)
		#        self.redirect('/{0}'.format(key.id()))
		time.sleep(0.1)
		self.redirect('/')

class Answer(db.Model):
	user = db.UserProperty()
	question_id = db.StringProperty()
	body = db.TextProperty()
	create_time = db.DateTimeProperty(auto_now_add = True)
	last_modified = db.DateTimeProperty(auto_now = True)
	has_modified = db.BooleanProperty()
	answervote = db.IntegerProperty()

	def render(self, render_full_text=False):
		if len(self.body) > 500 and not render_full_text:
			self.render_text = self.body[:500].replace('\n', '<br>') + ' ... (more) ...'
		else:
			self.render_text = self.body.replace('\n', '<br>')

		
		http = r'(https?://\w[^ \t<]*)'
		img_pattern = r'\.(png|jpg|gif)$'
		img = re.compile(img_pattern)


		local_img = re.compile(r'(localhost:\d+/pic/[^/ ]+)|({0}/pic/[^/ ]+)'.format(HOST_PATH))
		links = re.findall(http, self.render_text)

		for link in links:
		    if img.search(link) or local_img.search(link):
		        self.render_text = re.sub(r'({0})'.format(link), r'<a href="\1"><img src="\1" alt="Image"></a>', self.render_text)
		    else:
		        self.render_text = re.sub(r'({0})'.format(link), r'<a href="\1"> \1 </a>', self.render_text)            
		'''
		aid = str(self.key().id())
		votes = db.GqlQuery('select * from AnswerVote where question_id = :1 and answer_id = :2', self.question_id, aid)
		answervote = 0
		for vote in votes:
			answervote = answervote+vote.vote
		self.answervote=answervote
		'''

		self.cuser = users.get_current_user()

		if not render_full_text:
			self.show_permalink = True
		if self.user == users.get_current_user():
			self.is_editable = True
#		return render_str('answer_template.html', p = self)

	def refresh(self, question_id, answer_id):
		votes = db.GqlQuery('select * from AnswerVote where question_id = :1 and answer_id = :2', question_id, answer_id)
		answervote = 0
		for vote in votes:
			answervote = answervote+vote.vote
		self.answervote=answervote

class QuestionVote(db.Model):
	user = db.UserProperty()
	question_id = db.StringProperty()
	vote = db.IntegerProperty()

class AnswerVote(db.Model):
	user = db.UserProperty()
	question_id = db.StringProperty()
	answer_id = db.StringProperty()
	vote = db.IntegerProperty()


class AnswerEdit(webapp2.RequestHandler):    
	def get(self, question_id, answer_id):
		answer = Answer.get_by_id(int(answer_id))
		self.response.write(self.render(question_id, answer))

	def render(self, question_id, p=None):
		if p:
			p.body_str = p.body
			p.parent=question_id
		else:
			class p: pass
			p.body_str = ''
			p.parent=question_id

		return render_str('answer_edit_template.html', p=p)

class NewAnswer(AnswerEdit):
	def get(self, question_id):
		self.response.write(self.render(question_id=question_id))


class AnswerEntry(webapp2.RequestHandler):
	def post(self, question_id, answer_id=None):
		if not answer_id:
			post = Answer()
			post.user = users.get_current_user()
		else:
			# TODO Check if the blog post is oiwned by the current user
			post = Answer.get_by_id(int(answer_id))
			post.has_modified = True

		post.body = self.request.get('body')
		post.question_id=question_id
		post.answervote=0

		key = post.put()

		# memcache.delete(KEY)
		#        self.redirect('/{0}'.format(key.id()))
		time.sleep(0.1)
		self.redirect('/'+question_id)

class VoteQuestion(webapp2.RequestHandler):
	def get(self, question_id):
		user = users.get_current_user()
		action = self.request.get('action')
		
		q = db.GqlQuery('select * from QuestionVote where user = :1 and question_id = :2', user, question_id)
		if q.count() > 0:
			for result in q:
				result.delete()
		
		value = QuestionVote()
		value.user = user
		value.question_id = question_id
		if action == "up" or action == "upm":
			value.vote = 1
		else:
			value.vote = -1
		value.put()
		time.sleep(0.1)

		question = Question.get_by_id(int(question_id))
		question.refresh(question_id)
		question.put()
		time.sleep(0.1)

		
		if action.find('m') == -1:
			self.redirect('/'+question_id)
		else:
			self.redirect('/')

class VoteAnswer(webapp2.RequestHandler):
	def get(self, question_id, answer_id):
		user = users.get_current_user()
		action = self.request.get_all('action')
		action = action[0]

		q = db.GqlQuery('select * from AnswerVote where user = :1 and question_id = :2 and answer_id = :3', user, question_id, answer_id)
		if q.count() > 0:
			for result in q:
				result.delete()
		
		value = AnswerVote()
		value.user = user
		value.question_id = question_id
		value.answer_id = answer_id
		if action == "up":
			value.vote = 1
		else:
			value.vote = -1

		value.put()
		time.sleep(0.1)

		answer = Answer.get_by_id(int(answer_id))
		answer.refresh(question_id, answer_id)
		answer.put()


		time.sleep(0.1)
		self.redirect('/'+question_id)

		

app = webapp2.WSGIApplication([
	('/', Mainpage),
	('/index', Mainpage),
	('/createquestion', NewQuestion),
	('/([0-9]+)', ViewQuestion),
	('/([0-9]+)/post', QuestionEntry),
	('/([0-9]+)/createanswer', NewAnswer),
	('/([0-9]+)/([0-9]+)/answerpost', AnswerEntry),
	('/([0-9]+)/answerpost', AnswerEntry),
	('/post', QuestionEntry),
	('/([0-9]+)/vote', VoteQuestion),
	('/([0-9]+)/([0-9]+)/vote', VoteAnswer),
	('/([0-9]+)/edit', QuestionEdit),
	('/([0-9]+)/([0-9]+)/edit', AnswerEdit),

], debug=True)