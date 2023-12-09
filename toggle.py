import json


GYRO_CFG_PATH = '/home/arch/GPD/BMI260/gyro.json'

cfg = json.load(open(GYRO_CFG_PATH))

cfg['enable'] = not cfg['enable']
json.dump(cfg, open(GYRO_CFG_PATH, 'w'))
