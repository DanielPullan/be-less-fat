## Be Less Fat by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Weight loss data and visualisations
## 17/07/2019

## We're all about the metric system here. 🇪🇺
## Weight - kilograms (kg), height - metres (m), calories (kcal)

import sys

## Added help function just in case
## How long has emoji support existed?

## Example usage - python3 be-less-fat.py 90 1.8 1500 30
## For help - python3 be-less-fat.py help
## For Metallica - python3 be-less-fat.py 🤘

if sys.argv[1] == "help":
    print("the order is height, weight, calories, age, gender, activity")
    print("Activity is scale 1-5, 1 being potato, 5 being PT instructor")
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
    try: 
        gender = sys.argv[5]
    except IndexError:
        gender = "null"
    try: 
        activity = int(sys.argv[6])
    except IndexError:
        activity = "null"

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

def mifflin(height, weight, age, gender, activity):
    if gender == "male":
        calories_per_day = (10*weight) + (6.25 *height) - (5*age) + 5
    elif gender == "female":
        calories_per_day = (10*weight) + (6.25*height) - (5*age) - 161
    else:
        calories_per_day = "You dun goofed"

    calories_with_excercise = (calories_per_day*activity) 

    return calories_with_excercise


result = mifflin(height, weight, age, gender, activity)

print(result)

