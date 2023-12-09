import json
from time import sleep, time

from bmi260 import registers
from bmi260 import definitions
from bmi260.BMI270 import BMI270
from bmi260.config_file import bmi260_config_file

from dataclasses import dataclass
from libevdev import Device, InputEvent, EV_REL, EV_KEY, EV_ABS, EV_SYN


CFG_UPDATE_DELAY = 0.5

def get_sensor():
    # init
    sensor = BMI270(registers.I2C_SEC_ADDR)
    sensor.soft_reset()
    sensor.load_config_file(bmi260_config_file)

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

    return sensor


@dataclass
class VirtualPointerData:
    prev: int
    curr: float
    changed: bool

@dataclass
class VirtualPointer:
    x: VirtualPointerData
    y: VirtualPointerData


# init
sensor = get_sensor()

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
last_cfg_read_time = time()
cfg = json.load(open('/home/arch/GPD/BMI260/gyro.json'))

virt_ptr = VirtualPointer(
    VirtualPointerData(0, 0, False),
    VirtualPointerData(0, 0, False)
)

vel = [0, 0]

# run
while True:
    # load config
    if time() - last_cfg_read_time > CFG_UPDATE_DELAY:
        try:
            cfg = json.load(open('/home/arch/GPD/BMI260/gyro.json'))
            last_cfg_read_time = time()
            # print(cfg)
        except:
            sleep(CFG_UPDATE_DELAY)
            continue
        
        # check sensor
        if sensor.read_register(registers.INTERNAL_STATUS) == 0:
            sensor = get_sensor()
            print('sensor reinitialized')

    if (not cfg['enable']) or cfg['mode'] != 'mouse':
        sleep(CFG_UPDATE_DELAY)
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

    virt_ptr.x.curr -= vel[0] if abs(vel[0]) > 0.05 else 0
    virt_ptr.x.changed = True if abs(virt_ptr.x.curr - virt_ptr.x.prev) >= 1 else False

    virt_ptr.y.curr -= vel[1] if abs(vel[1]) > 0.05 else 0
    virt_ptr.y.changed = True if abs(virt_ptr.y.curr - virt_ptr.y.prev) >= 1 else False

    # print(f'{data} -> {vel} -> {virt_ptr}')

    # send events
    events = [
        InputEvent(EV_REL.REL_X, (int(virt_ptr.x.curr) - virt_ptr.x.prev) if virt_ptr.x.changed else 0),
        InputEvent(EV_REL.REL_Y, (int(virt_ptr.y.curr) - virt_ptr.y.prev) if virt_ptr.y.changed else 0),
        InputEvent(EV_SYN.SYN_REPORT, 0)
    ]
    gyro_inp.send_events(events)

    if abs(virt_ptr.x.curr - virt_ptr.x.prev) >= 1:
        virt_ptr.x.prev = int(virt_ptr.x.curr)

    if abs(virt_ptr.y.curr - virt_ptr.y.prev) >= 1:
        virt_ptr.y.prev = int(virt_ptr.y.curr)
