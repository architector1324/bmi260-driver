import json


table = {
    None: 'mouse',
    'mouse': None
}

cfg = json.load(open('/home/arch/GPD/BMI260/gyro.json'))
cfg['mode'] = table[cfg['mode']]
json.dump(cfg, open('/home/arch/GPD/BMI260/gyro.json', 'w'))
