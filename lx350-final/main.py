import webapp2
import jinja2
import os
import urllib
import re
import cgi
import time
import datetime

from google.appengine.ext import db
from google.appengine.api import memcache
from google.appengine.api import images
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
		query = {}
		self.user = users.get_current_user()

		self.users = users

		option = self.request.get('option')
		if option:
			query['option']=option
			option = '-'+option
		else:
			option='-create_time'
		self.posts = Question.all().order(option)
		self.answers = Answer.all()

		self.tags = sorted(set([j for i in self.posts for j in i.tags]))
		search_tag = self.request.get('tag')
		if search_tag:
			query['tag']=search_tag
			self.posts.filter('tags', search_tag)

		username = self.request.get('user')
		if username:
			if username.find('@')==-1:
				username=username+'@gmail.com'
			query['user']=username
			username = users.User(username)
			self.posts.filter('user', username)

		url='/index?'
		for (k,q) in query.items():
			url=url+'{0}={1}'.format(k, q)+'&'

		page = self.request.get('page')
		if not page:
			page = 0
			self.has_previous=False
		else:
			page = int(page)
			self.has_previous=True

		if page==1:
			self.previous_url=url.strip('&')
		else:
			self.previous_url=url+'page='+str(page-1)

		if page*10+10>=self.posts.count():
			self.has_next=False
			self.next_url=url.strip('&')
		else:
			self.has_next=True
			self.next_url=url+'page='+str(page+1)



		self.posts=self.posts[page*10:(page*10+10)]
		for post in self.posts:		
			post.render()
			post.put()
		time.sleep(0.1)

		self.response.write(render_str('index.html', p = self))


class ViewQuestion(webapp2.RequestHandler):
	def get(self, question_id):
		self.user = users.get_current_user()
		self.users = users
		
		self.question=Question.get_by_id(int(question_id))
		self.question.render(True)
		self.question.put()
		time.sleep(0.1)

		self.answers=db.GqlQuery('select * from Answer where question_id = :1 order by answervote desc', question_id)
		for answer in self.answers:
			answer.render()
			answer.put()
		time.sleep(0.1)
		if self.answers.count() == 0:
			self.viewanswer=False
		else:
			self.viewanswer=True

		self.question_id=question_id

		self.response.write(render_str('viewquestion.html', p = self))



class Question(db.Model):
	user = db.UserProperty()
	title = db.StringProperty()
	body = db.TextProperty()
	avatar = db.BlobProperty()
	tags = db.StringListProperty()
	create_time = db.DateTimeProperty(auto_now_add = True)
	last_modified = db.DateTimeProperty()
	has_modified = db.BooleanProperty()
	questionvote = db.IntegerProperty()
	render_text = db.TextProperty()
	is_editable = db.BooleanProperty()
	answernumber = db.IntegerProperty()

	def render(self, render_full_text=False):
		if len(self.body) > 500 and not render_full_text:
			self.render_text = self.body[:500].replace('\n', '<br>') + ' ... (more) ...'
		else:
			self.render_text = self.body.replace('\n', '<br>')

		
		http = r'(https?://\w[^ \t<]*)'
		img_pattern = r'\.(png|jpg|gif|jpeg|bmp)$'
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

		self.answernumber = db.GqlQuery('select * from Answer where question_id = :1', str(self.key().id())).count()

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

		post.title = self.request.get('title')
		post.body = self.request.get('body')
		post.tags = self.request.get('tags').split()
		avatar = self.request.get('img')
		if avatar:
			post.avatar = db.Blob(avatar)
		post.questionvote = 0

		date = datetime.datetime.now(EST())
		post.last_modified = date
		key = post.put()

		time.sleep(0.1)
		self.redirect('/')

class Answer(db.Model):
	user = db.UserProperty()
	question_id = db.StringProperty()
	title = db.StringProperty()
	body = db.TextProperty()
	avatar = db.BlobProperty()
	create_time = db.DateTimeProperty(auto_now_add = True)
	last_modified = db.DateTimeProperty()
	has_modified = db.BooleanProperty()
	answervote = db.IntegerProperty()
	render_text = db.TextProperty()
	is_editable = db.BooleanProperty()

	def render(self):
		
		self.render_text = self.body.replace('\n', '<br>')

		http = r'(https?://\w[^ \t<]*)'
		img_pattern = r'\.(png|jpg|gif|jpeg|bmp)$'
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
		else:
			class p: pass
			p.body_str = ''
		
		p.parent=question_id
		p.user = users.get_current_user()
		p.users = users
		return render_str('createanswer.html', p=p)

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
		avatar = self.request.get('img')
		if avatar:
			post.avatar = db.Blob(avatar)
		post.answervote=0
		date = datetime.datetime.now(EST())
		post.last_modified = date

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


		time.sleep(0.2)
		self.redirect('/'+question_id)

class EST(datetime.tzinfo):
    def utcoffset(self, dt):
      return datetime.timedelta(hours=0)

    def dst(self, dt):
        return datetime.timedelta(0)

class Image(webapp2.RequestHandler):
    def get(self):
        greeting = Question.get(self.request.get('img_id'))
        if greeting.avatar:
            self.response.headers['Content-Type'] = 'image/png'
            self.response.out.write(greeting.avatar)
        else:
            self.response.out.write('No image')

class AnswerImage(webapp2.RequestHandler):
    def get(self):
        greeting = Answer.get(self.request.get('img_id'))
        if greeting.avatar:
            self.response.headers['Content-Type'] = 'image/png'
            self.response.out.write(greeting.avatar)
        else:
            self.response.out.write('No image')

class RSS(webapp2.RequestHandler):
	def get(self):
		self.posts = Question.all().order('-create_time')
		self.user = users.get_current_user()
		self.time = datetime.datetime.now(EST())
		self.users = users
		self.response.headers['Content-Type'] = 'application/rss+xml'
		self.response.write(render_str('rss.html', p=self))

class questionRSS(webapp2.RequestHandler):
	def get(self, question_id):
		self.question = Question.get_by_id(int(question_id))
		self.posts = Answer.all().order('-create_time')
		self.posts = self.posts.filter('question_id', question_id)
		self.user = users.get_current_user()
		self.time = datetime.datetime.now(EST())
		self.users = users
		self.response.headers['Content-Type'] = 'application/rss+xml'
		self.response.write(render_str('questionrss.html', p=self))
		

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
	('/img', Image),
	('/ansimg', AnswerImage),
	('/rss', RSS),
	('/([0-9]+)/rss',questionRSS),

], debug=True)