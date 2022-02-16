## BLF Flask by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Another test flask app for Be Less Fat.
## First attempted 29/07/2019, current attempt 14/02/2022.

## Never made a thing with flask before. This project may be a great test topic.

from flask import Flask, request, render_template, make_response, redirect
import pymysql
from config import *

app = Flask(__name__)

the_cookie = "Site"
the_good_cookie = "Canada_On_Guard_For_Thee"
the_other_cookie = "Ja_Vi_Elsker_Dette_Landet"

conn = pymysql.connect(host=dbhost, port=dbport, user=dbuser, passwd=dbpass, db=dbname, autocommit=True)

# Splashy thing. Cookies, link to login page, personal website and github.
@app.route('/')
def home():
	cookie = str(request.cookies.get(the_cookie))
	if cookie == the_good_cookie:
		user = str(request.cookies.get('User'))
		user_logged_in = True
	else:
		user = "Guest"
		user_logged_in = False

	weight = 77
	height = 1.6
	bmi = 32
	status = "Work to do"

	return render_template("index.html", username=user, weight = weight, height=height, bmi=bmi, status=status)


@app.route('/login', methods=['GET', 'POST'])
def login():

	if request.method == 'POST':
		# get login details from form
		form_username = request.form['username']
		form_password = request.form['password']
		form_pin = request.form['pin']

		cur = conn.cursor()
		cur.execute("SELECT * FROM users where username = %s;", (form_username))
		cur.close()
		results = cur.fetchone()

		username = str(results[1])
		password = str(results[2])
		pin = str(results[3])

		if form_username == username and form_password == password and form_pin == pin:
			resp = make_response(redirect('/me'))
			resp.set_cookie(the_cookie, the_good_cookie)
			resp.set_cookie('User', username)
			return resp
		else:
			print('login failed')
		return "login failed"

	title = "Login"
	return render_template("login.html", title=title)

@app.route('/logout', methods=['GET', 'POST'])
def logout():
	res = make_response(redirect('/'))
	res.set_cookie(the_cookie, the_other_cookie)
	return res

@app.route('/me')
def me():
	title = "me"
	cookie = str(request.cookies.get(the_cookie))
	user = str(request.cookies.get('User'))

	cur = conn.cursor()
	cur.execute("SELECT * FROM weight WHERE user = %s ORDER  BY id DESC LIMIT  1;", (user))
	cur.close()
	results = cur.fetchone()

	weight = str(results[3])

	return render_template("me.html", title=title, user=user, weight=weight)

@app.route('/track', methods=['GET', 'POST'])
def track():
	cookie = str(request.cookies.get(the_cookie))
	user = str(request.cookies.get('User'))

	if request.method == 'POST':
		# get login details from form
		form_weight= request.form['weight']

		weight = form_weight

		date = "1994-06-13"

		if cookie == the_good_cookie:
			cur = conn.cursor()
			# cur.execute("INSERT INTO weight (user, logdate, weight) values(%s, %s, %s;", (user, date, weight))
			cur.execute("INSERT INTO weight (user, logdate, weight) values (%s, %s, %s);", (user, date, weight))

			cur.close()
		else:
			print("tracking failed")

		return render_template("result.html", weight=form_weight, user=user)

	return render_template("track.html")



	return title

@app.route('/history')
def history():
	title = "history"
	return title

if __name__ == "__main__":
	app.run(debug=True)
