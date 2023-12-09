import json
from time import sleep, time

from bmi260 import registers
from bmi260 import definitions
from bmi260.BMI270 import BMI270
from bmi260.config_file import bmi260_config_file

from libevdev import Device, InputEvent, EV_REL, EV_KEY, EV_ABS, EV_SYN


# init
sensor = BMI270(registers.I2C_SEC_ADDR)
sensor.soft_reset()
sensor.load_config_file(bmi260_config_file)

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
sensor.set_mode(definitions.PERFORMANCE_MODE)

# sensor.set_acc_range(definitions.ACC_RANGE_2G)
# sensor.set_acc_odr(definitions.ACC_ODR_200)
# sensor.set_acc_bwp(definitions.ACC_BWP_OSR4)

sensor.set_gyr_range(definitions.GYR_RANGE_2000)
sensor.set_gyr_odr(definitions.GYR_ODR_200)
sensor.set_gyr_bwp(definitions.GYR_BWP_OSR4)

sensor.disable_fifo_header()
sensor.enable_data_streaming()
# sensor.enable_acc_filter_perf()
sensor.enable_gyr_noise_perf()
sensor.enable_gyr_filter_perf()

sensor.disable_acc()
sensor.disable_aux()
sensor.enable_gyr()

last_cfg_read_time = time()
cfg = json.load(open('/home/arch/GPD/BMI260/gyro.json'))

pos = [[0, 0, False], [0, 0, False]]
vel = [0, 0]

# run
while True:
    # load config
    if time() - last_cfg_read_time > 1:
        try:
            cfg = json.load(open('/home/arch/GPD/BMI260/gyro.json'))
            last_cfg_read_time = time()
            # print(cfg)
        except:
            sleep(1)
            continue

    if cfg['mode'] != 'mouse':
        sleep(1)
        continue

    planes = {
        'xy' : (0, 1),
        'xz': (2, 1)
    }

    plane = planes.get(cfg['plane'])
    if plane is None:
        print(f'unexpected plane "{cfg["plane"]}"')
        sleep(1)
        continue

    # read data
    data = sensor.get_gyr_data()

    vel[0] *= 0.8
    vel[1] *= 0.8

    vel[0] += cfg['sens'] * data[plane[0]]
    vel[1] += cfg['sens'] * data[plane[1]]

    pos[0][1] -= vel[0] if abs(vel[0]) > 0.05 else 0
    pos[0][2] = True if abs(pos[0][0] - pos[0][1]) >= 1 else False

    pos[1][1] -= vel[1] if abs(vel[1]) > 0.05 else 0
    pos[1][2] = True if abs(pos[1][0] - pos[1][1]) >= 1 else False

    # print(f'{data} -> {vel} -> {pos}')

    # send events
    events = [
        InputEvent(EV_REL.REL_X, (int(pos[0][1]) - pos[0][0]) if pos[0][2] else 0),
        InputEvent(EV_REL.REL_Y, (int(pos[1][1]) - pos[1][0]) if pos[1][2] else 0),
        InputEvent(EV_SYN.SYN_REPORT, 0)
    ]
    gyro_inp.send_events(events)

    if abs(pos[0][0] - pos[0][1]) >= 1:
        pos[0][0] = int(pos[0][1])

    if abs(pos[1][0] - pos[1][1]) >= 1:
        pos[1][0] = int(pos[1][1])
