#!/usr/bin/env python

##########################################################
# This extends the reflex_smarts ReFlex class and adds a series
# of preset moves
# Eric Schneider
##########################################################
# TODO: Setting servo speed is implemented here but not in firmware.
# Waiting on firmware implementation

import rospy
from math import floor
from copy import deepcopy
import sys

from std_msgs.msg import Float64

from reflex_base_services import *

# interface
# 1 arguments       = apply to whole hand
# 3 arguments       = apply to each finger
# 2,4,6 arguments   = apply to each (finger, command) pair

# position parameters
ROT_CYL = 0.0       # radians rotation
ROT_SPH = 0.8       # radians rotation
ROT_PINCH = 1.57    # radians rotation

OPEN = 0            # radians tendon spool
PROBE_POS = 0.8     # radians tendon spool
DOF_POS = 3.25
DOF_WAITTIME = 1    # seconds between dof_tour steps
HOW_HARDER = 0.1    # radians step size for tightening and loosening


class ReFlex_Smarts(ReFlex):
    def __init__(self):
        super(ReFlex_Smarts, self).__init__()

        # called on per-finger or full-hand basis
        self.SMART_FINGER_COMMANDS = ['open',
                                      'close',
                                      'preshape_probe',
                                      'tighten',
                                      'loosen']

        # called only on full-hand basis
        self.HAND_COMMANDS = ['cylinder',
                              'spherical',
                              'pinch',
                              'fingerwalk',
                              'align_all',
                              'dof',
                              'burnin']

    # Parses modes and turns them into control_modes for control_loop
    def __command_smart_finger(self, finger, mode):
        i = self.FINGER_MAP[finger]
        if mode == 'open':
            self.working[i] = True
            self.open(i, self.SERVO_SPEED_MAX)
        elif mode == 'close':
            self.working[i] = True
            self.close(i, self.SERVO_SPEED_MAX)
        elif mode == 'preshape_probe':
            self.working[i] = True
            self.preshape_probe(i, self.SERVO_SPEED_MAX)
        elif mode == 'tighten':
            self.working[i] = True
            self.tighten(i, self.SERVO_SPEED_MAX/2.0)
        elif mode == 'loosen':
            self.working[i] = True
            self.loosen(i, self.SERVO_SPEED_MAX/2.0)
        else:
            rospy.logwarn("reflex_smarts: received unknown finger command: %s",
                          mode)
        self.reset_hist(self.working[i], i)

    def command_smarts(self, speed, *args):
        # 1 arg = hand command
        # 3 arg = finger commands
        # 2, 4, 6 arg = [finger, mode, (finger, mode, (finger, mode))]

        flag = False

        if len(args) == 1:
            if args[0] in self.HAND_COMMANDS:
                if args[0] == 'cylinder':   self.set_cylindrical(speed)
                if args[0] == 'spherical':  self.set_spherical(speed)
                if args[0] == 'pinch':      self.set_pinch(speed)
                if args[0] == 'dof':        self.dof_tour(speed)
                if args[0] == 'burnin':     self.burnin(speed)
                if args[0] == 'fingerwalk': self.fingerwalk(speed)
                if args[0] == 'align_all':  self.align_all(speed)
            elif args[0] in self.BASE_FINGER_COMMANDS:
                self._ReFlex__command_base_finger('f1', args[0])
                self._ReFlex__command_base_finger('f2', args[0])
                self._ReFlex__command_base_finger('f3', args[0])
                self.servo_speed = [speed, speed, speed]
            else:
                self.__command_smart_finger('f1', args[0])
                self.__command_smart_finger('f2', args[0])
                self.__command_smart_finger('f3', args[0])
                self.servo_speed = [speed, speed, speed]
                if args[0] not in self.SMART_FINGER_COMMANDS:
                    flag = True

        elif len(args) == 3:
            for i in range(3):
                ID = self.FINGER_MAP.keys()[i]
                if args[i] in self.BASE_FINGER_COMMANDS:
                    self._ReFlex__command_base_finger(ID, args[i])
                else:
                    self.__command_smart_finger(ID, args[i])
                    if args[i] not in self.SMART_FINGER_COMMANDS:
                        flag = True

            self.servo_speed = [speed, speed, speed]
        elif len(args) in [2, 4, 6]:
            IDs = [args[2 * j] for j in range(len(args) / 2)]
            modes = [args[2 * (j + 1) - 1] for j in range(len(args) / 2)]

            for j in range(len(IDs)):
                if modes[j] in self.BASE_FINGER_COMMANDS:
                    self._ReFlex__command_base_finger(IDs[j], modes[j])
                else:
                    self.__command_smart_finger(IDs[j], modes[j])
                self.servo_speed[j] = speed
            for mode in modes:
                if mode not in self.BASE_FINGER_COMMANDS and\
                   mode not in self.SMART_FINGER_COMMANDS:
                    flag = True
        else:
            rospy.loginfo("reflex_smarts: didn't recognize input, given %s",
                          args)
            flag = True

        rospy.loginfo("reflex_smarts:command_smarts: commanded fingers")
        rospy.loginfo("self.working = %s, self.control_mode: %s",
                      str(self.working), str(self.control_mode))

        while any(self.working) and not rospy.is_shutdown():
            rospy.sleep(0.01)
        return flag

    def open(self, finger_index, speed=1.0):
        rospy.loginfo("reflex_smarts: Opening finger %d", finger_index + 1)
        self.move_finger(finger_index, self.TENDON_MIN, speed)

    def close(self, finger_index, speed=1.0):
        rospy.loginfo("reflex_smarts: Closing finger %d", finger_index + 1)
        self.move_finger(finger_index, self.TENDON_MAX, speed)

    def preshape_probe(self, finger_index, speed=1.0):
        rospy.loginfo("reflex_smarts: Finger %d to preshape position",
                      finger_index + 1)
        self.move_finger(finger_index, PROBE_POS, speed)

    def tighten(self, finger_index, speed=1.0, spool_delta=HOW_HARDER):
        rospy.loginfo("reflex_smarts: Tighten finger %d", finger_index + 1)
        self.move_finger(finger_index,
                         self.hand.finger[finger_index].spool + spool_delta,
                         speed)

    def loosen(self, finger_index, speed=1.0, spool_delta=HOW_HARDER):
        rospy.loginfo("reflex_smarts: Tightening finger %d", finger_index + 1)
        self.move_finger(finger_index,
                         self.hand.finger[finger_index].spool - spool_delta,
                         speed)

    def set_cylindrical(self, speed=1.0):
        rospy.loginfo("reflex_smarts: Going to cylindrical pose")
        self.move_preshape(ROT_CYL, speed)

    def set_spherical(self, speed=1.0):
        rospy.loginfo("reflex_smarts: Going to spherical pose")
        self.move_preshape(ROT_SPH, speed)

    def set_pinch(self, speed=1.0):
        rospy.loginfo("reflex_smarts: Going to pinch pose")
        self.move_preshape(ROT_PINCH, speed)

    # Runs hand through its range of motion, using fingers and preshape joint
    def dof_tour(self, speed=1.0):
        rospy.loginfo("reflex_smarts: Exploring hand DOF...")
        self.move_preshape(ROT_CYL, speed)
        rospy.sleep(DOF_WAITTIME)
        for i in range(3):
            rospy.logwarn("Moving finger %d", i + 1)
            self.move_finger(i, DOF_POS, speed)
            rospy.sleep(DOF_WAITTIME)
            self.open(i, speed)
            rospy.sleep(DOF_WAITTIME)
        for pos in [ROT_SPH, ROT_PINCH, ROT_CYL]:
            self.move_preshape(pos, speed)
            rospy.sleep(DOF_WAITTIME)
        return

    def burnin(self, speed=1.0):
        rospy.loginfo("reflex_smarts:burnin")
        self.move_preshape(ROT_CYL, speed)
        while any(self.working) and not rospy.is_shutdown():
            rospy.sleep(0.01)
        for i in range(3):
            self.move_finger(i, DOF_POS, speed)
            while any(self.working) and not rospy.is_shutdown():
                rospy.sleep(0.01)
            self.open(i, speed)
            while any(self.working) and not rospy.is_shutdown():
                rospy.sleep(0.01)
        return

    # Performs a set routine to tighten fingers and walk object into solid grip
    def fingerwalk(self, speed=1.0, in_step=0.6, out_step=1.0):
        rospy.loginfo("reflex_smarts: Starting fingerwalk...")
        current_state = deepcopy(self.hand)
        counter = 0     # fail-safe to prevent overheating motors

        if len(self.hand_hist) > 0:
            while not any([self.hand_hist[0].palm.contact[i] for i in range(11)])\
                    and not all([self.finger_full_contact(i) for i in range(3)])\
                    and (counter < floor(1.8 / in_step))\
                    and not rospy.is_shutdown():

                for i in range(3):
                    self.move_finger(i, current_state.finger[i].spool+in_step,
                                     speed)
                    current_state.finger[i].spool += in_step
                while any(self.working) and not rospy.is_shutdown():
                    rospy.sleep(0.01)

                self.move_finger(0, current_state.finger[0].spool - out_step,
                                 speed)
                while any(self.working) and not rospy.is_shutdown():
                    rospy.sleep(0.01)

                self.move_finger(0, current_state.finger[0].spool, speed)
                while any(self.working) and not rospy.is_shutdown():
                    rospy.sleep(0.01)

                self.move_finger(1, current_state.finger[0].spool - out_step,
                                 speed)
                while any(self.working) and not rospy.is_shutdown():
                    rospy.sleep(0.01)

                self.move_finger(1, current_state.finger[0].spool, speed)
                while any(self.working) and not rospy.is_shutdown():
                    rospy.sleep(0.01)

                counter += 1
                rospy.loginfo("reflex_smarts: Completed %d fingerwalk cycles",
                              counter)
            return
        else:
            rospy.loginfo("reflex_smarts: No Hand data read, can't fingerwalk")
            return

    # Finds the avg of the three finger spool values and sets them all to that
    def align_all(self, speed=1.0):
        avg_spool = sum([self.hand.finger[i].spool for i in range(3)]) / 3.0
        rospy.loginfo("reflex_smarts: Set all fingers to avg spool pos: %f",
                      avg_spool)
        for i in range(3):
            self.move_finger(i, avg_spool, speed)


if __name__ == '__main__':
    rospy.init_node('ReflexServiceNode')
    reflex_hand = ReFlex_Smarts()

    sh2 = MoveFingerService(reflex_hand)
    s2 = "/reflex/move_finger"
    rospy.loginfo("reflex_smarts:__main__: Advertising the %s service", s2)
    s2 = rospy.Service(s2, MoveFinger, sh2)

    sh3 = MovePreshapeService(reflex_hand)
    s3 = "/reflex/move_preshape"
    rospy.loginfo("reflex_smarts:__main__: Advertising the %s service", s3)
    s3 = rospy.Service(s3, MovePreshape, sh3)

    sh4 = StatusDumpService(reflex_hand)
    s4 = "/reflex/status_dump"
    rospy.loginfo("reflex_smarts:__main__: Advertising the %s service", s4)
    s4 = rospy.Service(s4, Empty, sh4)

    sh5 = KillService(reflex_hand)
    s5 = "/reflex/kill_current"
    rospy.loginfo("reflex_smarts:__main__: Advertising the %s service", s5)
    s5 = rospy.Service(s5, Empty, sh5)

    sh6 = CommandSmartService(reflex_hand)
    s6 = "/reflex/command_smarts"
    rospy.loginfo("reflex_smarts:__main__: Advertising the %s service", s6)
    s6 = rospy.Service(s6, CommandHand, sh6)

    r_fast = rospy.Rate(50)
    r_slow = rospy.Rate(1)
    while not rospy.is_shutdown():
        if reflex_hand.hand_publishing:
            r_slow.sleep()
        else:
            reflex_hand._ReFlex__control_loop()
            r_fast.sleep()
