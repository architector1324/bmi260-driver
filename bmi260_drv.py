import json
from time import sleep, time

from bmi270 import registers
from bmi270 import definitions
from bmi270.BMI270 import BMI270

from libevdev import Device, InputEvent, EV_REL, EV_KEY, EV_ABS, EV_SYN


# init
GYRO_MAX_SENS = 3

sensor = BMI270(registers.I2C_SEC_ADDR)
sensor.load_config_file()

gyro_dev = Device()
gyro_dev.name = 'BMI260 gyro'

gyro_dev.enable(EV_KEY.BTN_LEFT)
gyro_dev.enable(EV_KEY.BTN_RIGHT)
# gyro_dev.enable(EV_ABS.ABS_RX)
# gyro_dev.enable(EV_ABS.ABS_RY)
gyro_dev.enable(EV_REL.REL_X)
gyro_dev.enable(EV_REL.REL_Y)

gyro_inp = gyro_dev.create_uinput_device()
print('new uinput test device at {}'.format(gyro_inp.devnode))

# config
sensor.set_mode(definitions.NORMAL_MODE)
sensor.set_acc_range(definitions.ACC_RANGE_2G)
sensor.set_gyr_range(definitions.GYR_RANGE_1000)
sensor.set_acc_odr(definitions.ACC_ODR_200)
sensor.set_gyr_odr(definitions.GYR_ODR_200)
sensor.set_acc_bwp(definitions.ACC_BWP_NORMAL)
sensor.set_gyr_bwp(definitions.GYR_BWP_NORMAL)

sensor.disable_fifo_header()
sensor.enable_data_streaming()
sensor.enable_acc_filter_perf()
sensor.enable_gyr_noise_perf()
sensor.enable_gyr_filter_perf()

last_cfg_read_time = time()
cfg = json.load(open('/home/arch/GPD/BMI260/gyro.json'))

# run
while True:
    sensor.enable_gyr()
    sensor.enable_acc()
    sensor.enable_aux()
    sensor.enable_temp()

    # load config
    if time() - last_cfg_read_time > 1:
        cfg = json.load(open('/home/arch/GPD/BMI260/gyro.json'))
        last_cfg_read_time = time()
        # print(cfg)

    if cfg['mode'] != 'mouse':
        sleep(1)
        continue

    # read data
    sens = GYRO_MAX_SENS * cfg['sens']

    data = [int(min(GYRO_MAX_SENS, e * sens)) for e in sensor.get_gyr_data()]
    # print(data)

    planes = {
        'xy' : (data[0], data[1]),
        'xz': (data[2], data[1])
    }

    rel = planes.get(cfg['plane'])
    if rel is None:
        print(f'unexpected plane "{cfg["plane"]}"')
        sleep(1)
        continue

    # print(rel)

    # send events
    events = [
        InputEvent(EV_REL.REL_X, -rel[0]),
        InputEvent(EV_REL.REL_Y, -rel[1]),
        InputEvent(EV_SYN.SYN_REPORT, 0)
    ]
    gyro_inp.send_events(events)
