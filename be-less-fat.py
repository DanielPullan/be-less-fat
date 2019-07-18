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
		print(daily_calorie_intake)
	except IndexError:
		daily_calorie_intake = 0
	try:
		age = sys.argv[4]
		print(age)
	except IndexError:
		age = 0

## Calculate BMI. bmi = weight/height²
## Calculate minimum height weight for height (does age come into account?)

def bmiCalc(weight, height, daily_calorie_intake, age):
	weight = weight
	height = height
	daily_calorie_intake = daily_calorie_intake
	bmi = weight / (height**2)
	return bmi

bmi = bmiCalc(weight, height, daily_calorie_intake, age)

## I think the safe bmi values vary by age so need to take that into account

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