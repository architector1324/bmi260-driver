import os
import json
import fcntl

from time import sleep, time

from bmi260 import registers
from bmi260 import definitions
from bmi260.BMI270 import BMI270
from bmi260.config_file import bmi260_config_file

from dataclasses import dataclass
from libevdev import Device, InputEvent, EV_REL, EV_KEY, EV_ABS, EV_SYN, EV_MSC, INPUT_PROP_ACCELEROMETER


@dataclass
class VirtualPointerData:
    prev: int
    curr: float
    changed: bool

@dataclass
class VirtualPointer:
    vel: [int, int]
    x: VirtualPointerData
    y: VirtualPointerData


class BMI260Driver:
    PLANES = {
        'xy' : (0, 1),
        'xz': (2, 1)
    }

    MODE_EVENT = {
        'mouse': (EV_REL.REL_X, EV_REL.REL_Y, EV_SYN.SYN_REPORT),
        'gamepad': (EV_ABS.ABS_X, EV_ABS.ABS_Y, EV_ABS.ABS_Z, EV_ABS.ABS_RX, EV_ABS.ABS_RY, EV_ABS.ABS_RZ, EV_MSC.MSC_TIMESTAMP, EV_SYN.SYN_REPORT),
    }

    GAMEPAD_ID = {
        'bustype': 0x3,
        'vendor': 0x045e,
        'product': 0x028e,
        'version': 0x110
    }

    GAMEPAD_KEY_EVENTS = [
        EV_KEY.BTN_THUMBL,
        EV_KEY.BTN_THUMBR,
        EV_KEY.BTN_TL,
        EV_KEY.BTN_TR,
        EV_KEY.BTN_WEST,
        EV_KEY.BTN_NORTH,
        EV_KEY.BTN_SOUTH,
        EV_KEY.BTN_EAST,
        EV_KEY.BTN_SELECT,
        EV_KEY.BTN_START
    ]

    GAMEPAD_ABS_EVENTS = [
        EV_ABS.ABS_X,
        EV_ABS.ABS_Y,
        EV_ABS.ABS_RX,
        EV_ABS.ABS_RY,
        EV_ABS.ABS_Z,
        EV_ABS.ABS_RZ,
        EV_ABS.ABS_HAT0X,
        EV_ABS.ABS_HAT0Y,
    ]

    def __init__(self, gyro_cfg_path, gyro_cfg_update_delay=0.5):
        self.gyro_cfg_path = gyro_cfg_path
        self.gyro_cfg_update_delay = gyro_cfg_update_delay

        self.load_cfg()

        self.init_sensor()
        self.init_dev()

        self.last_update_time = time()

        self.virt_ptr = VirtualPointer(
            [0, 0],
            VirtualPointerData(0, 0, False),
            VirtualPointerData(0, 0, False)
        )

    # FIXME: think about reinit device when 'mode' has been changed
    def init_dev(self):
        # gamepad
        self.gamepad_dev = None

        for i in range(0, 100):
            try:
                fd = open(f'/dev/input/event{i}', 'rb')
            except:
                continue

            fcntl.fcntl(fd, fcntl.F_SETFL, os.O_NONBLOCK)

            dev = Device(fd)
            print(f'Found {i}: "{dev.name}" ("/dev/input/event{i}")')

            if dev.name == 'Microsoft X-Box 360 pad':
                print(f'gamepad device is recognised "/dev/input/event{i}"')
                self.gamepad_dev = dev
                self.gamepad_dev.grab()

        # gyro
        self.gyro_dev = Device()
        self.gyro_dev.name = 'BMI260 gyro'

        if self.gamepad_dev:
            self.gyro_dev.id = self.GAMEPAD_ID

        if self.gyro_cfg['mode'] == 'mouse':
            self.gyro_dev.enable(EV_KEY.BTN_LEFT)
            self.gyro_dev.enable(EV_KEY.BTN_RIGHT)
            self.gyro_dev.enable(EV_REL.REL_X)
            self.gyro_dev.enable(EV_REL.REL_Y)
        elif (self.gyro_cfg['mode'] == 'gamepad') and (self.gamepad_dev is not None):
            self.gyro_dev.enable(EV_MSC.MSC_TIMESTAMP)
            self.gyro_dev.enable(INPUT_PROP_ACCELEROMETER)

            for e in self.GAMEPAD_KEY_EVENTS:
                self.gyro_dev.enable(e)

            for e in self.GAMEPAD_ABS_EVENTS:
                self.gyro_dev.enable(e, self.gamepad_dev._absinfos[e])

        self.gyro_inp = self.gyro_dev.create_uinput_device()
        print('create new bmi260 device at {}'.format(self.gyro_inp.devnode))

    def init_sensor(self):
        # init
        self.sensor = BMI270(registers.I2C_SEC_ADDR)
        self.sensor.soft_reset()
        self.sensor.load_config_file(bmi260_config_file)

        # config
        self.sensor.set_mode(definitions.PERFORMANCE_MODE)

        # self.sensor.set_acc_range(definitions.ACC_RANGE_2G)
        # self.sensor.set_acc_odr(definitions.ACC_ODR_200)
        # self.sensor.set_acc_bwp(definitions.ACC_BWP_OSR4)

        self.sensor.set_gyr_range(definitions.GYR_RANGE_2000)
        self.sensor.set_gyr_odr(definitions.GYR_ODR_200)
        self.sensor.set_gyr_bwp(definitions.GYR_BWP_OSR4)

        self.sensor.disable_fifo_header()
        self.sensor.enable_data_streaming()
        # self.sensor.enable_acc_filter_perf()
        self.sensor.enable_gyr_noise_perf()
        self.sensor.enable_gyr_filter_perf()

        self.sensor.disable_aux()
        self.sensor.enable_gyr()
        self.sensor.enable_acc()

    def load_cfg(self):
        self.last_cfg_read_time = time()
        self.gyro_cfg = json.load(open(self.gyro_cfg_path))

    def process_mouse(self):
        if (not self.gyro_cfg['enable']):
            sleep(self.gyro_cfg_update_delay)
            self.sensor.disable_gyr()
            return

        plane = self.PLANES.get(self.gyro_cfg['plane'])
        if plane is None:
            print(f'unexpected plane "{self.gyro_cfg["plane"]}"')
            sleep(1)
            return

        # read data
        self.sensor.enable_gyr()

        data = self.sensor.get_gyr_data()

        self.virt_ptr.vel[0] *= 0.8
        self.virt_ptr.vel[1] *= 0.8

        self.virt_ptr.vel[0] += self.gyro_cfg['sens'] * data[plane[0]]
        self.virt_ptr.vel[1] += self.gyro_cfg['sens'] * data[plane[1]]

        self.virt_ptr.x.curr -= self.virt_ptr.vel[0] if abs(self.virt_ptr.vel[0]) > 0.05 else 0
        self.virt_ptr.x.changed = True if abs(self.virt_ptr.x.curr - self.virt_ptr.x.prev) >= 1 else False

        self.virt_ptr.y.curr -= self.virt_ptr.vel[1] if abs(self.virt_ptr.vel[1]) > 0.05 else 0
        self.virt_ptr.y.changed = True if abs(self.virt_ptr.y.curr - self.virt_ptr.y.prev) >= 1 else False

        # print(f'{data} -> {vel} -> {virt_ptr}')

        # send events
        events = [
            InputEvent(EV_REL.REL_X, (int(self.virt_ptr.x.curr) - self.virt_ptr.x.prev) if self.virt_ptr.x.changed else 0),
            InputEvent(EV_REL.REL_Y, (int(self.virt_ptr.y.curr) - self.virt_ptr.y.prev) if self.virt_ptr.y.changed else 0),
            InputEvent(EV_SYN.SYN_REPORT, 0)
        ]
        self.gyro_inp.send_events(events)

        if abs(self.virt_ptr.x.curr - self.virt_ptr.x.prev) >= 1:
            self.virt_ptr.x.prev = int(self.virt_ptr.x.curr)

        if abs(self.virt_ptr.y.curr - self.virt_ptr.y.prev) >= 1:
            self.virt_ptr.y.prev = int(self.virt_ptr.y.curr)

    def process_gamepad(self):
        # forward gamepad events
        for e in self.gamepad_dev.events():
            # if e.code in self.MODE_EVENT[self.gyro_cfg['mode']]:
            # print(e)
            self.gyro_inp.send_events([e])

        if (not self.gyro_cfg['enable']):
            self.virt_ptr = VirtualPointer(
                [0, 0],
                VirtualPointerData(0, 0, False),
                VirtualPointerData(0, 0, False)
            )
            self.sensor.disable_acc()
            self.sensor.disable_gyr()
            sleep(0.005)
            return

        # read data
        self.sensor.enable_gyr()
        self.sensor.enable_acc()

        gyro = self.sensor.get_raw_gyr_data()
        acc = self.sensor.get_raw_acc_data()
        tm = self.sensor.get_sensor_time()

        rel = (
            int(self.gyro_cfg['sens'] * acc[0]),
            int(self.gyro_cfg['sens'] * acc[1]),
            int(self.gyro_cfg['sens'] * acc[2]),
            int(self.gyro_cfg['sens'] * gyro[0]),
            int(self.gyro_cfg['sens'] * gyro[1]),
            int(self.gyro_cfg['sens'] * gyro[2]),
        )

        # send events
        events = [
            InputEvent(EV_MSC.MSC_TIMESTAMP, tm),
            InputEvent(EV_ABS.ABS_RX, rel[0]),
            InputEvent(EV_ABS.ABS_RY, rel[1]),
            InputEvent(EV_ABS.ABS_RZ, rel[2]),
            InputEvent(EV_ABS.ABS_X, rel[3]),
            InputEvent(EV_ABS.ABS_Y, rel[4]),
            InputEvent(EV_ABS.ABS_Z, rel[5]),
            InputEvent(EV_SYN.SYN_REPORT, 0),
        ]
        self.gyro_inp.send_events(events)
        sleep(0.005)

    def mainloop(self):
        while True:
            # load config
            if time() - self.last_cfg_read_time > self.gyro_cfg_update_delay:
                try:
                    self.gyro_cfg  = json.load(open(self.gyro_cfg_path))
                    self.last_cfg_read_time = time()
                    # print(self.gyro_cfg )
                except:
                    sleep(self.gyro_cfg_update_delay)
                    continue
                
                # check sensor
                if self.sensor.read_register(registers.INTERNAL_STATUS) == 0:
                    self.init_sensor()
                    print('sensor reinitialized')

            # process
            if self.gyro_cfg['mode'] == 'mouse':
                self.process_mouse()
            elif self.gyro_cfg['mode'] == 'gamepad':
                self.process_gamepad()

            # print(f'ft: {time() - self.last_update_time}')
            self.last_update_time = time()
            sleep(0.0005)


# run
bmi260_drv = BMI260Driver('/home/arch/GPD/BMI260/gyro.json')
bmi260_drv.mainloop()
