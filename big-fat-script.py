## Be Less Fat by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Weight loss data and visualisations
## 17/07/2019

## We're all about the metric system here. 🇪🇺
## Weight - kilograms (kg), height - metres (m), calories (kcal)

## For help - python3 miffler.py help
## For Metallica - python3 miffler.py 🤘


## Imports

import sys

## Get information from command

if sys.argv[1] == "help":
    print("the order is height, weight, calories, age, gender, activity")
    print("Activity is scale 1-5, 1 being potato, 5 being PT instructor")
    raise SystemExit
elif sys.argv[1] == "🤘":
    print("Metallica ruuuuuuules")
    raise SystemExit
else:
    height = float(sys.argv[1])
    weight = float(sys.argv[2])
    try:
        daily_calorie_intake = int(sys.argv[3])
    except IndexError:
        daily_calorie_intake = 0
    try:
        age = int(sys.argv[4])
    except IndexError:
        age = "👀"
    try: 
        gender = sys.argv[5]
    except IndexError:
        gender = "null"
    try: 
        activity = sys.argv[6]
    except IndexError:
        activity = "null"

## Sort out activity data

def multiplier(activity):
    multiplier  = {
        1: 1.2,
        2: 1.375,
        3: 1.55,
        4: 1.725,
        5: 1.9
    }
    activity = multiplier.get(activity, "null")
    return activity
    activity = multiplier(activity)

## Add functions

def mifflin(height, weight, age, gender, activity):
    if gender == "male":
        calories_per_day = (10*weight) + (6.25 *height) - (5*age) + 5
    elif gender == "female":
        calories_per_day = (10*weight) + (6.25*height) - (5*age) - 161
    else:
        calories_per_day = "You dun goofed"
    calories_with_excercise = (calories_per_day*activity) 
    return calories_with_excercise

def met(weight, activity):
    calories_per_hour = (activity*weight)
    return calories_per_hour

def hr(age):
    hrmax = 202 - (0.55 * age)
    lower_limit = (55 * hrmax) / 100
    higher_limit = (85 * hrmax) / 100
    return hrmax, lower_limit, higher_limit

def bmiCalc(weight, height):
    bmi = weight / (height**2)
    return bmi

woo = bmiCalc(weight, height)

print(woo)
