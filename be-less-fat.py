## Be Less Fat by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Weight loss data and visualisations
## 17/07/2019

## We're all about the metric system here. 🇪🇺
## Weight - kilograms (kg), height - metres (m), calories (kcal)

import sys

## Added help function just in case
## How long has emoji support existed?

if sys.argv[1] == "help":
	print("the order is height, weight, calories, age")
	raise SystemExit
elif sys.argv[1] == "🤘":
	print("Metallica ruuuuuuules")
	raise SystemExit
else:
	height = float(sys.argv[1])
	weight = int(sys.argv[2])
	try:
		daily_calorie_intake = int(sys.argv[3])
	except IndexError:
		daily_calorie_intake = 0
	try:
		age = int(sys.argv[4])
	except IndexError:
		age = "👀"

## Calculate BMI. bmi = weight/height²
## Calculate minimum height weight for height

## According to NHS, adult bmi doesn't take into account age, gender or muscle mass (or pregnancy)
## Children bmi does take into account age, so age will need to be required
## For now, if age < 18, just end.

def bmiCalc(weight, height, daily_calorie_intake, age):
	bmi = weight / (height**2)
	return bmi

bmi = int(bmiCalc(weight, height, daily_calorie_intake, age))

bmi_response = 0

## I think the safe bmi values vary by age so need to take that into account

if age == "👀" or age >= 18:
	if bmi < 18.5:
		bmi_response = ("You are very underweight")
	elif bmi > 18.5 and bmi < 25:
		bmi_response = ("You are a normal weight")
	elif bmi > 25 and bmi < 35:
		bmi_response = ("You are overweight")
	elif bmi > 35:
		bmi_response = ("You are very overweight.")
	else: 
		bmi_response = ("Error")
elif age < 18:
	bmi_response = ("As you are under 18, Be Less Fat currently won't work for you.")
else:
	bmi_response = ("issue")


print(bmi_response)

## TODO: Create charts and stuff here.
## Maybe xkcd plot whilst in development?

## TODO: Child BMI measurements

## TODO: Write a config file with data, then website creates self using data?
## Would like to use flask or web.py though

## This is a one time only type deal. Doesn't take into account previous/historical data
## Only usable as a rough guide

webpage_data = """var height = "%s";
var weight = "%s";
var daily_calorie_intake = "%s";
var age = "%s";
var bmi = "%s";
var bmi_response = "%s";


document.getElementById('height').innerHTML = height;
document.getElementById('weight').innerHTML = weight;
document.getElementById('daily_calorie_intake').innerHTML = daily_calorie_intake;
document.getElementById('age').innerHTML = age;
document.getElementById('bmi').innerHTML = bmi;
document.getElementById('bmi_response').innerHTML = bmi_response;

"""%(height, weight, daily_calorie_intake, age, bmi, bmi_response)

f = open('one-day-data/one-day-data.js', 'w')
f.write(webpage_data)
f.close()