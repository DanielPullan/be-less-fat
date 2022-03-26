## Heart Rate Maximum Calc by Dan Pullan (https:/danielpullan.co.uk)
## 31/07/2019

import sys

if sys.argv[1] == "help":
    print("the order is age")
    raise SystemExit
elif sys.argv[1] == "🤘":
    print("Metallica ruuuuuuules")
    raise SystemExit
else:
    age = int(sys.argv[1])

def hr(age):
	hrmax = 202 - (0.55 * age)
	lower_limit = (55 * hrmax) / 100
	higher_limit = (85 * hrmax) / 100
	return hrmax, lower_limit, higher_limit

result = hr(age)

print(result)