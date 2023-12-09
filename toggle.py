import json


cfg = json.load(open('/home/arch/GPD/BMI260/gyro.json'))
cfg['enable'] = not cfg['enable']
json.dump(cfg, open('/home/arch/GPD/BMI260/gyro.json', 'w'))
