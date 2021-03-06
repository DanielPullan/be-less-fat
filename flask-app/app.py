## Flask app by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Test flask app for Be Less Fat. First time making a website with flask.
## 29/07/2019

## Never made a thing with flask before. This project may be a great test topic.

from flask import Flask, request, render_template, make_response, redirect
import pymysql
from config import *

app = Flask(__name__)

host = where_did_you_come_from
user = the_greatest_username_ever
pw = the_most_secure_password_ever
database = johnny_five_is_alive
the_cookie = c_is_for_cookies_not_OSs
the_good_cookie = rust_gang_represent_safely
conn = pymysql.connect(host=host, port=3306, user=user, passwd=pw, db=database, autocommit=True)


# Home is for linking to things and saying hello. Also cookies.
@app.route('/')
def home():
	cookie = str(request.cookies.get(the_cookie))

	if cookie == the_good_cookie:
		usercookie = str(request.cookies.get('User'))
		user_logged_in = True
	else:
		usercookie = "Guest"
		user_logged_in = False


	return render_template("index.html", username=usercookie)


# Login is for logging in, with a link to registering
@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'POST':
		# get login details from form
		username = request.form['username']
		password = request.form['password']
		pin = request.form['pin']

		# mysql query to check if details exist/are correct
		cur = conn.cursor()
		cur.execute("SELECT * FROM login where username = %s;", (username))
		cur.close()
		results = cur.fetchone()

	#TODO: blah stuff. get the data from the data in blah to become variables and then do the whole if the form password matches the database one, create the cookie and shit

		security = 0

		submittedusername = str(results[1])
		submittedpassword = str(results[2])
		submittedpin = str(results[3])

		if submittedusername == username:
			security = security + 1
		else: 
			security = 0

		if submittedpassword == password:
			security = security + 1
		else:
			security = 0
		if submittedpin == pin:
			security = security + 1
		else:
			security = 0

		if security == 3:
			resp = make_response(redirect('/'))
			resp.set_cookie(the_cookie, the_good_cookie)
			resp.set_cookie('User', username)
			return resp
		else:
			print(security)
			print(submittedusername)
			print(submittedpassword)
			print(submittedpin)
			print(username)
			print(password)
			print(pin)
			return "login failed"

	return render_template("login.html")


# Logging out is just for logging out, nothing else
@app.route('/logout', methods=['GET', 'POST'])
def logout():
	res = make_response(redirect('/'))
	res.set_cookie(the_cookie, 'Quebec')
	return res


# There's probably a way of making this useful
@app.route('/get')
def getcookie():
	cookie = str(request.cookies.get(the_cookie))
	if cookie == the_good_cookie:
		return cookie
	else:
		res = make_response(redirect('/stare'))
		res.set_cookie(the_cookie, 'Quebec')
		return res

# The greatest redirect ever
@app.route('/stare')
def stare():
	return render_template('stare.html')

# This is for users to get an overview of their data
@app.route('/overview')
def overview():
	# Check that user is logged in

	# SQL query to get all the user data

	# Sort sql data into variables

	# Run variables through various calculations

	# Turn the results of those calculations into things I can return a template

	return render_template('overview.html')


# This is for users to submit their fake data. Please no real data.
# I'm sure real data probably comes under a tonne of privacy laws and I'm just
# not equipped to deal with that responsibility.
# Seriously, learn to protect your data. https://learning.mozilla.org/en-US/activities/protect-your-data/
@app.route('/submit-data')
def submitdata():
	# check that user is logged in

	# form stuff

	# sql query to submit form stuff to database

	# redirect to a dead meme

	return render_template('submit-data.html')


@app.route('/bmi-calculator', methods=['GET', 'POST'])
def bmicalculator():
	if request.method == 'POST':
		# get info from form
		weight = int(request.form['weight'])
		height = int(request.form['height'])
		age = int(request.form['age'])
		result = weight / (height**2)
		bmi = int(result)
		bmi_response = 0
		if age == "👀" or age >= 18:
			if bmi < 18.5:
				bmi_result =  "You are very underweight"
			elif bmi > 18.5 and bmi < 25:
				bmi_result =  "You are a normal weight"
			elif bmi > 25 and bmi < 35:
				bmi_result =  "You are overweight"
			elif bmi > 35:
				bmi_result =  "You are very overweight."
			else: 
				bmi_result =  "Error"
		elif age < 18:
			bmi = ("Unknown")
			bmi_result =  "As you are under 18, Be Less Fat currently won't work for you."
		else:
			bmi_result =  "issue"

		return render_template("bmi-result.html", bmi_result=bmi_result)
	return render_template("bmi-calculator.html")



if __name__ == "__main__":
	app.run(debug=True)
