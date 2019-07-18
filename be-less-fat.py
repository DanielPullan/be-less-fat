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
		daily_calorie_intake = sys.argv[3]
	except IndexError:
		daily_calorie_intake = 0
	try:
		age = int(sys.argv[4])
	except IndexError:
		age = 0

## Calculate BMI. bmi = weight/height²
## Calculate minimum height weight for height

## According to NHS, adult bmi doesn't take into account age, gender or muscle mass (or pregnancy)
## Children bmi does take into account age, so age will need to be required
## For now, if age < 18, just end.

def bmiCalc(weight, height, daily_calorie_intake, age):
	weight = weight
	height = height
	daily_calorie_intake = daily_calorie_intake
	bmi = weight / (height**2)
	return bmi

bmi = bmiCalc(weight, height, daily_calorie_intake, age)

## I think the safe bmi values vary by age so need to take that into account
if age > 18:
	if bmi < 18.5:
		print("You are very underweight")
	elif bmi > 18.5 and bmi < 25:
		print("You are a normal weight")
	elif bmi > 25 and bmi < 35:
		print("You are overweight")
	elif bmi > 35:
		print("You are very overweight.")
	else: 
		print("Error")
else:
	print("As you are under 18, Be Less Fat currently won't work for you.")