## Food Calorie Calculator by Dan Pullan (https://danielpullan.co.uk/projects/food-calorie-calculator)
## 28/07/2019

## We're all about the metric system here. 🇪🇺
## Calories (kcal), weight (g)

import sys

if sys.argv[1] == "help":
	print("the order is amount(g), calorie (kcal), goal calorie(kcal)")
	raise SystemExit
else:
	amount = int(sys.argv[1])
	source_calorie = int(sys.argv[2])
	goal_calorie = int(sys.argv[3])

def calorieCalc(amount, source_calorie, goal_calorie):
	calorie_per_gram = int(source_calorie/amount)
	return calorie_per_gram

blah = calorieCalc(amount, source_calorie, goal_calorie)

print(blah)
