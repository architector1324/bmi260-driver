import json
import argparse

# config
GYRO_CFG_PATH = '/home/arch/GPD/BMI260/gyro.json'
cfg = json.load(open(GYRO_CFG_PATH))

dpi = [0.28, 0.42, 0.64, 0.8, 1.0]

parser = argparse.ArgumentParser('Gyro toggler')
parser.add_argument('--dpi', action='store_true')

# run
args = parser.parse_args()

if args.dpi:
    cfg['sens'] = next((v for v in dpi if cfg['sens'] < v), dpi[0])
else:
    cfg['enable'] = not cfg['enable']

json.dump(cfg, open(GYRO_CFG_PATH, 'w'))

