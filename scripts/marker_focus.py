#!/usr/bin/env python  
import roslib
import rospy
import tf
from threading import Thread, Lock

import time

from operator import sub
from math import *
from nao_msgs.msg import JointAnglesWithSpeed
from sensor_msgs.msg import JointState

transform_lock = Lock()
latest_transform = None
transform_changed = False

class HeadStateSubscriber(Thread):

    head_state_lock = None

    head_state_sub = None
    current_head_yaw   = None
    current_head_pitch = None

    def __init__(self):
        Thread.__init__(self)
        self.head_state_lock = Lock()

    def update_head_state(self, data):
        #print data.name[0], data.position[0]
        #print data.name[1], data.position[1]

        self.head_state_lock.acquire(True)

        self.current_head_yaw   = data.position[0]
        self.current_head_pitch = data.position[1]

        self.head_state_lock.release()

    def get_current_head_positions(self):

        self.head_state_lock.acquire(True)

        position = (self.current_head_yaw, 
                    self.current_head_pitch)

        self.head_state_lock.release()

        return position

    def run(self):
        self.head_state_sub = rospy.Subscriber("joint_states", JointState, self.update_head_state)
        rospy.spin()

class HeadMoverPublisher(Thread):

    speed = 0.02
    head_mover_pub = None

    head_state_manager = None

    def __init__(self, head_state_manager):
        Thread.__init__(self)
        self.head_state_manager = head_state_manager
        self.head_mover_pub = rospy.Publisher('joint_angles', JointAnglesWithSpeed, queue_size = 10)

    def run(self):
        r = rospy.Rate(10)
        while not rospy.is_shutdown():
      
            transform_lock.acquire(True)
            
            angles = None

            global latest_transform, transform_changed
            if latest_transform != None and transform_changed == True:
                transform_changed = False
                angles = self.get_angles(latest_transform)

            transform_lock.release()

            if angles != None:
                print angles
                dirs   = self.get_dirs(angles)
                #print dirs
                self.move_head(dirs)

            r.sleep()

    def move_head(self,dirs):
        message = JointAnglesWithSpeed()
        message.joint_names  = ["HeadYaw", "HeadPitch"]
        message.joint_angles = [dirs[0]*2, dirs[1]*1]
        message.speed = self.speed
        self.head_mover_pub.publish(message)
        #time.sleep(30)
        #self.stop_head()

    def stop_head(self):
        current_head_pos = self.head_state_manager.get_current_head_positions()
        stop_message = JointAnglesWithSpeed()
        stop_message.joint_names  = ["HeadYaw", "HeadPitch"]
        stop_message.joint_angles = [current_head_pos[0],
                                     current_head_pos[1]] 
        stop_message.speed = 1.0
        self.head_mover_pub.publish(stop_message)

    def get_angles(self, trans):
        return {"angle_up":   degrees(atan(-trans[1]/trans[2])),
                "angle_left": degrees(atan(-trans[0]/trans[2]))}

    def get_dirs(self, angles):
        horizontal_dir = 1 if angles["angle_left"] > 0 else -1
        vertical_dir   = 1 if angles["angle_up"]   < 0 else -1
        return (horizontal_dir, vertical_dir)

class MarkerTransformListener():

    listener = None

    def __init__(self):
        self.listener = tf.TransformListener()

    def did_transform_change(self, old_transform, new_transform):
        if old_transform == None and new_transform != None:
            return True
        else:
            #print map(abs, map(sub, old_transform, new_transform))
            return all(map(float.__ge__, 
                map(abs, map(sub, old_transform, new_transform)),
                (0.01, 0.01, 0.01)))

    def run(self):
        rate = rospy.Rate(10.0)
        self.listener.waitForTransform("/CameraTop_frame1", "4x4_2", rospy.Time(), rospy.Duration(4.0))
        while not rospy.is_shutdown():
            try:
                now = rospy.Time().now()
                self.listener.waitForTransform("/CameraTop_frame1", "4x4_2", now, rospy.Duration(4.0))
                
                transform_lock.acquire(True)
                global latest_transform, transform_changed
                (new_transform, _) = self.listener.lookupTransform('/CameraTop_frame1', '/4x4_2', now)
                
                if self.did_transform_change(latest_transform, new_transform):
                    transform_changed = True
                    latest_transform  = new_transform
                
                transform_lock.release()
                #print latest_transform
            except (tf.LookupException, tf.ConnectivityException, tf.ExtrapolationException):
                continue

if __name__ == '__main__':
    
    rospy.init_node('marker_focus')
    
    head_state_sub  = HeadStateSubscriber()
    head_controller = HeadMoverPublisher(head_state_sub)

    head_state_sub.daemon = True
    head_state_sub.start()

    head_controller.daemon = True
    head_controller.start()


    marker_listener = MarkerTransformListener()
    marker_listener.run()
