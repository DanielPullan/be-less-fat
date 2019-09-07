## Be Less Fat by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Weight loss data and visualisations
## 17/07/2019

## We're all about the metric system here. 🇪🇺
## Weight - kilograms (kg), height - metres (m), calories (kcal)

import sys

## Added help function just in case
## How long has emoji support existed?

## Example key - python3 met.py weight activity
## Example usage - python3 met.py 80 jumping-jacks
## Alt example usage - python3 met.py 80 3             
## For help - python3 met.py help
## For Metallica - python3 met.py 🤘

if sys.argv[1] == "help":
    print("the order is weight, activity")
    print("See https://danielpullan.co.uk/projects/met-calculator for activity value")
    print("This page currently isn't live.")
    raise SystemExit
elif sys.argv[1] == "🤘":
    print("Metallica ruuuuuuules")
    raise SystemExit
else:
    weight = int(sys.argv[1])
    activity = sys.argv[2]

def multiplier(activity):
    multiplier  = {
        "1": 1.2,
        "2": 1.375,
        "3": 1.55,
        "4": 1.725,
        "5": 1.9,
        "sleeping": 0.9,
        "telly": 1,
        "desk-work": 1.8,
        "slow-walk": 2,
        "light-bike": 3,
        "home-excercise": 3.5,
        "medium-bike": 4, 
        "stationary-bike": 5.5,
        "jogging": 5,
        "pushups": 8,
        "pullups": 8,
        "jumping-jacks": 8,
        "jogging": 8
    }
    activity = float(multiplier.get(activity, "null"))
    return activity

activity = multiplier(activity)

def met(weight, activity):
    calories_per_hour = (activity*weight)
    return calories_per_hour

result = met(weight, activity)

print(result)

