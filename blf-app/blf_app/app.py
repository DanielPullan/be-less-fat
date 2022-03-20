## BLF Flask by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Another test flask app for Be Less Fat.
## First attempted 29/07/2019, current attempt 14/02/2022.

## Never made a thing with flask before. This project may be a great test topic.

from flask import Flask, request, render_template, make_response, redirect, session, url_for
import pymysql
from datetime import datetime # might use time instead
import time # might use datetime instead
import tzlocal # might not keep this
from config import *

app = Flask(__name__)
app.secret_key = "Canada_On_Guard_For_Thee"

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
		
		cur = conn.cursor()
		cur.execute("SELECT * FROM alert ORDER  BY id DESC LIMIT  1;")
		cur.close()
		alert_result = cur.fetchone()

		weight = 77 # TODO: get this from db
		height = 1.6 # TODO: get this from db
		bmi = 32 # TODO: get this from db
		status = alert_result[1]
	else:
		user = "Guest"
		user_logged_in = False
		weight = 0
		height = 0
		bmi = 0
		status = "u ain't logged in"
	
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
	
	res.delete_cookie('User')
	return res

@app.route('/me')
def me():
	title = "Me"
	cookie = str(request.cookies.get(the_cookie))
	user = str(request.cookies.get('User'))

	cur = conn.cursor()
	cur.execute("SELECT * FROM weight WHERE user = %s ORDER  BY id DESC LIMIT  1;", (user))
	cur.close()
	results = cur.fetchone()

	weight = str(results[3])

	return render_template("me.html", title=title, user=user, weight=weight, username=user)

@app.route('/track-weight', methods=['GET', 'POST'])
def trackweight():
	cookie = str(request.cookies.get(the_cookie))
	user = str(request.cookies.get('User'))
	title = "Track Weight"

	if request.method == 'POST':
		# get login details from form
		form_weight= request.form['weight']

		weight = form_weight

		date = int(time.time())

		if cookie == the_good_cookie:
			cur = conn.cursor()
			cur.execute("INSERT INTO weight (user, logdate, weight) values (%s, %s, %s);", (user, date, weight))
			cur.close()
		else:
			print("tracking failed")

		return render_template("result-weight.html", weight=form_weight, user=user, username=user  )

	return render_template("track-weight.html", username=user, title=title)

@app.route('/track-food', methods=['GET', 'POST'])
def trackfood():
	cookie = str(request.cookies.get(the_cookie))
	user = str(request.cookies.get('User'))
	title = "Track Food"

	if request.method == 'POST':
		# get login details from form
		form_food= request.form['food']
		form_calories = request.form['calories']

		food = form_food
		calories = form_calories

		date = int(time.time())

		if cookie == the_good_cookie:
			cur = conn.cursor()
			cur.execute("INSERT INTO calories (user, logdate, food, calories) values (%s, %s, %s, %s);", (user, date, food, calories))
			cur.close()
		else:
			print("tracking failed")

		return render_template("result-food.html", food=form_food, calories=form_calories, user=user, username=user  )

	return render_template("track-food.html", username=user, title=title)

@app.route('/delete-last-weight')
def deletelastweight():
	cookie = str(request.cookies.get(the_cookie))
	user = str(request.cookies.get('User'))

	if cookie == the_good_cookie:
		cur = conn.cursor()
		cur.execute("DELETE FROM weight WHERE user = %s ORDER  BY id DESC LIMIT  1;", (user))
		cur.close()

		return redirect('/me')

@app.route('/weight-history')
def weighthistory():
	cookie = str(request.cookies.get(the_cookie))
	user = str(request.cookies.get('User'))
	# Get last 5 weights

	cur = conn.cursor()
	cur.execute("SELECT user, logdate, weight FROM weight WHERE user = %s ORDER  BY id DESC LIMIT  5;", (user))
	cur.close()
	results = cur.fetchall()

	title = "Weight History"
	return render_template("weight-history.html", title=title, username=user, results=results)

@app.route('/food-history')
def foodhistory():
	cookie = str(request.cookies.get(the_cookie))
	user = str(request.cookies.get('User'))

	secondsinday = 86400

	currentdateunix = int(time.time()) # get current date in unix timestamp

	dateneeded = currentdateunix - secondsinday # take current date, remove 24 hours worth of seconds and store that value

	print(dateneeded) # check value
	print(currentdateunix) # check value

	cur = conn.cursor() # open db connection
	cur.execute("SELECT user, food, calories FROM calories WHERE logdate > %s AND user = %s;", (dateneeded, user)) # run the query
	cur.close() # close db connection
	results = cur.fetchall() # store our result from db in a value

	print(results) # print all of our googles

	totalcalories = 0

	for x in results:
		totalcalories = totalcalories + x[2]
		print(totalcalories)

	title = "Food History"

	return render_template("food-history.html", title=title, username=user, results=results, totalcalories=totalcalories)


@app.route('/notice')
def notice():
	title="Notice"
	return render_template("notice.html", title=title)

if __name__ == "__main__":
	app.run(host='0.0.0.0',debug=True)
