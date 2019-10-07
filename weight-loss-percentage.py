## Be Less Fat by Dan Pullan (https://danielpullan.co.uk/projects/be-less-fat)
## Weight loss data and visualisations
## 17/07/2019

## We're all about the metric system here. 🇪🇺
## Weight - kilograms (kg), height - metres (m), calories (kcal)

import sys

## Added help function just in case
## How long has emoji support existed?

## Example key - python3 weight-loss-percentage.py start_weight current_weight
## Example usage - python3 weight-loss-percentage 93.3 77.8
## Alt example usage - python3 weight-loss-percentage 70 63             
## For help - python3 met.py help
## For Metallica - python3 met.py 🤘

if sys.argv[1] == "help":
    print("the order is start_weight, current_weight")
    raise SystemExit
elif sys.argv[1] == "🤘":
    print("Metallica ruuuuuuules")
    raise SystemExit
else:
    start_weight = float(sys.argv[1])
    current_weight = float(sys.argv[2])


def percentage_calculator(start_weight, current_weight):
    weight_loss = start_weight - current_weight
    percentage = int((weight_loss / start_weight) * 100)
    return percentage

result = percentage_calculator(start_weight, current_weight)

print(result)