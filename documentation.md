# Be Less Fat

Daniel Pullan (https://danielpullan.co.uk)

## About Be Less Fat

Be Less Fat is a python application designed towards visualising fitness data.

### Values Used

height - User's height in cm. Someone who is 1.6m would be 160cm.

weight - User's weight in kg. 80kg would be written as 80.

calories - Calories daily calorie consumption in kcal. On average, men should have 2500, women 2000. 2500kcal would be written as 2500.

age - User's age in years. 30 years would be written as 30.

gender - User's biological gender. Male would be written as male. No idea whether transgender users would have a different value after transitioning. Check with doctors if required. 

activity - **This one is weird and may require rethinking.** In one script, it's used for a multiplier of daily activity (1-5) and is an integer. In another script, it's a string and possible answers can be things like "pushups" and jogging. These activities and responses are assigned MET values.

### Usage

All scripts support `help` and `🤟`. `help` will give you example usages. `🤟` will print `metallica rules` and quit the script.

#### Be Less Fat

be-less-fat.py weight height daily_calories age

`python3 be-less-fat.py 90 180 1500 30`

#### Met

met.py weight activity

`python3 met.py 80 3`

#### Miffler

miffler.py height weight daily_calories age gender activity

`python3 miffler.py 160 80 1400 25 male 2`