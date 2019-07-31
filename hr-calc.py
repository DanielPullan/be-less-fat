## Heart Rate Maximum Calc by Dan Pullan (https:/danielpullan.co.uk)
## 31/07/2019

age = 25

hrmax = 202 - (0.55 * age)

lower_limit =  (55 * hrmax) / 100

higher_limit = (85 * hrmax) / 100

print(int(lower_limit), int(higher_limit))

print(int(hrmax))