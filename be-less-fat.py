## Be Less Fat by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Weight loss data and visualisations
## 17/07/2019

## We're all about the metric system here.
## Weight - kilograms (kg), height - metres (m), calories (kcal)

import sys

if sys.argv[1] == "help":
	print("the order is height, weight, calories, age")
else:
	height = float(sys.argv[1])
	weight = int(sys.argv[2])
	daily_calorie_intake = int(sys.argv[3])
	age = int(sys.argv[4])	

	def bmiCalc(weight, height, daily_calorie_intake, age):
		weight = weight
		height = height
		daily_calorie_intake = daily_calorie_intake
		bmi = weight / (height**2)
		return bmi

	bmi = bmiCalc(weight, height, daily_calorie_intake, age)


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