import os
import json
import fcntl

from time import sleep, time

from bmi260 import registers
from bmi260 import definitions
from bmi260.BMI270 import BMI270
from bmi260.config_file import bmi260_config_file

from dataclasses import dataclass
from libevdev import Device, InputEvent, EV_REL, EV_KEY, EV_ABS, EV_SYN


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
        'gamepad': (EV_ABS.ABS_RX, EV_ABS.ABS_RY, EV_SYN.SYN_REPORT),
        'gamepad_r': (EV_ABS.ABS_RX, EV_ABS.ABS_RY, EV_SYN.SYN_REPORT),
        'gamepad_l': (EV_ABS.ABS_X, EV_ABS.ABS_Y, EV_SYN.SYN_REPORT)
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

    GAMEPAD_DEV_PATH = '/dev/input/event24'

    def __init__(self, gyro_cfg_path, gyro_cfg_update_delay=0.5):
        self.gyro_cfg_path = gyro_cfg_path
        self.gyro_cfg_update_delay = gyro_cfg_update_delay

        self.load_cfg()

        self.init_sensor()
        self.init_dev()

        self.virt_ptr = VirtualPointer(
            [0, 0],
            VirtualPointerData(0, 0, False),
            VirtualPointerData(0, 0, False)
        )

    # FIXME: think about reinit device when 'mode' has been changed
    def init_dev(self):
        # gamepad
        try:
            self.gamepad_dev_fd = open(self.GAMEPAD_DEV_PATH, 'rb')
            fcntl.fcntl(self.gamepad_dev_fd, fcntl.F_SETFL, os.O_NONBLOCK)

            self.gamepad_dev = Device(self.gamepad_dev_fd)

            if self.gamepad_dev.has_property(EV_ABS):
                print('gamepad device is not recognised!')
                self.gamepad_dev = None
        except:
            self.gamepad_dev = None

        # gyro
        self.gyro_dev = Device()
        self.gyro_dev.name = 'BMI260 gyro'

        if self.gyro_cfg['mode'] == 'mouse':
            self.gyro_dev.enable(EV_KEY.BTN_LEFT)
            self.gyro_dev.enable(EV_KEY.BTN_RIGHT)
            self.gyro_dev.enable(EV_REL.REL_X)
            self.gyro_dev.enable(EV_REL.REL_Y)
        elif (self.gyro_cfg['mode'] in ('gamepad', 'gamepad_l', 'gamepad_r')) and (self.gamepad_dev is not None):
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

        self.sensor.disable_acc()
        self.sensor.disable_aux()
        self.sensor.enable_gyr()

    def load_cfg(self):
        self.last_cfg_read_time = time()
        self.gyro_cfg = json.load(open(self.gyro_cfg_path))

    def process_mouse(self, plane):
        if (not self.gyro_cfg['enable']):
            sleep(self.gyro_cfg_update_delay)
            return

        # read data
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

    def process_gamepad(self, plane):
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
            sleep(0.005)
            return

        # read data
        data = self.sensor.get_raw_gyr_data()

        rel = (
            self.gyro_cfg['sens'] * data[plane[0]],
            self.gyro_cfg['sens'] * data[plane[1]]
        )

        self.virt_ptr.x.curr += rel[0]
        self.virt_ptr.y.curr += rel[1]

        ev = (
            EV_ABS.ABS_X if self.gyro_cfg['mode'] == 'gamepad_l' else EV_ABS.ABS_RX,
            EV_ABS.ABS_Y if self.gyro_cfg['mode'] == 'gamepad_l' else EV_ABS.ABS_RY
        )

        self.virt_ptr.x.curr = max(self.gamepad_dev.absinfo[ev[0]].minimum, min(self.gamepad_dev.absinfo[ev[0]].maximum, self.virt_ptr.x.curr))
        self.virt_ptr.y.curr = max(self.gamepad_dev.absinfo[ev[1]].minimum, min(self.gamepad_dev.absinfo[ev[1]].maximum, self.virt_ptr.y.curr))

        # send events
        events = [
            InputEvent(ev[0], int(self.virt_ptr.x.curr)),
            InputEvent(ev[1], int(self.virt_ptr.y.curr)),
            InputEvent(EV_SYN.SYN_REPORT, 0)
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

            plane = self.PLANES.get(self.gyro_cfg['plane'])
            if plane is None:
                print(f'unexpected plane "{self.gyro_cfg["plane"]}"')
                sleep(1)
                continue

            # process
            if self.gyro_cfg['mode'] == 'mouse':
                self.process_mouse(plane)
            elif self.gyro_cfg['mode'] in ('gamepad', 'gamepad_l', 'gamepad_r'):
                self.process_gamepad(plane)


# run
bmi260_drv = BMI260Driver('/home/arch/GPD/BMI260/gyro.json')
bmi260_drv.mainloop()
