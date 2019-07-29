## Flask app by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Test flask app for Be Less Fat. First time making a website with flask.
## 29/07/2019

## Never made a thing with flask before. This project may be a great test topic.

from flask import Flask, escape, request
import sys

app = Flask(__name__)

@app.route('/')
def hello():
	name = request.args.get("name", "world")
	return f'Hello {escape(name)}!'

@app.route('/f')
def calorie():
	amountURL = request.args.get("amount", "0")
	source_calorieURL = request.args.get("source_calorie", "0")
	goal_calorieURL = request.args.get("goal_calorie", "0")

	amount = int(amountURL)
	source_calorie = int(source_calorieURL)
	goal_calorie = int(goal_calorieURL)

	calorie_per_gram = int(source_calorie/amount)
	return f'Blah blah blah {escape(calorie_per_gram)}!'