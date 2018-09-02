"""
Lidar
"""

import time
import math
import pickle
import serial
import numpy as np
from donkeycar.utils import norm_deg, dist, deg2rad, arr_to_img
from PIL import Image, ImageDraw

class RPLidar(object):
    '''
    https://github.com/SkoltechRobotics/rplidar
    '''
    def __init__(self, port='/dev/ttyUSB0'):
        from rplidar import RPLidar
        self.port = port
        self.distances = [] #a list of distance measurements 
        self.angles = [] # a list of angles corresponding to dist meas above
        self.lidar = RPLidar(self.port)
        self.lidar.clear_input()
        time.sleep(1)
        self.on = True
        #print(self.lidar.get_info())
        #print(self.lidar.get_health())


    def update(self):
        scans = self.lidar.iter_scans(550)
        while self.on:
            try:
                for scan in scans:
                    self.distances = [item[2] for item in scan]
                    self.angles = [item[1] for item in scan]
            except serial.serialutil.SerialException:
                print('serial.serialutil.SerialException from Lidar. common when shutting down.')

    def run_threaded(self):
        return self.distances, self.angles

    def shutdown(self):
        self.on = False
        time.sleep(2)
        self.lidar.stop()
        self.lidar.stop_motor()
        self.lidar.disconnect()


class LidarPlot(object):
    '''
    takes the raw lidar measurements and plots it to an image
    '''
    PLOT_TYPE_LINE = 0
    PLOT_TYPE_CIRC = 1
    def __init__(self, resolution=(500,500),
        max_dist=5000, #mm
        radius_plot=3,
        plot_type=PLOT_TYPE_CIRC):
        self.frame = Image.new('RGB', resolution)
        self.max_dist = max_dist
        self.rad = radius_plot
        self.resolution = resolution
        if plot_type == self.PLOT_TYPE_CIRC:
            self.plot_fn = self.plot_circ
        else:
            self.plot_fn = self.plot_line
            

    def plot_line(self, img, dist, theta, max_dist, draw):
        '''
        scale dist so that max_dist is edge of img (mm)
        and img is PIL Image, draw the line using the draw ImageDraw object
        '''
        center = (img.width / 2, img.height / 2)
        max_pixel = min(center[0], center[1])
        dist = dist / max_dist * max_pixel
        if dist < 0 :
            dist = 0
        elif dist > max_pixel:
            dist = max_pixel
        theta = np.radians(theta)
        sx = math.cos(theta) * dist + center[0]
        sy = math.sin(theta) * dist + center[1]
        ex = math.cos(theta) * (dist + self.rad) + center[0]
        ey = math.sin(theta) * (dist + self.rad) + center[1]
        fill = 128
        draw.line((sx,sy, ex, ey), fill=(fill, fill, fill), width=1)
        
    def plot_circ(self, img, dist, theta, max_dist, draw):
        '''
        scale dist so that max_dist is edge of img (mm)
        and img is PIL Image, draw the circle using the draw ImageDraw object
        '''
        center = (img.width / 2, img.height / 2)
        max_pixel = min(center[0], center[1])
        dist = dist / max_dist * max_pixel
        if dist < 0 :
            dist = 0
        elif dist > max_pixel:
            dist = max_pixel
        theta = np.radians(theta)
        sx = int(math.cos(theta) * dist + center[0])
        sy = int(math.sin(theta) * dist + center[1])
        ex = int(math.cos(theta) * (dist + 2 * self.rad) + center[0])
        ey = int(math.sin(theta) * (dist + 2 * self.rad) + center[1])
        fill = 128

        draw.ellipse((min(sx, ex), min(sy, ey), max(sx, ex), max(sy, ey)), fill=(fill, fill, fill))

    def plot_scan(self, img, distances, angles, max_dist, draw):
        for dist, angle in zip(distances, angles):
            self.plot_fn(img, dist, angle, max_dist, draw)
            
    def run(self, distances, angles):
        '''
        takes two lists of equal length, one of distance values, the other of angles corresponding to the dist meas 
        '''
        self.frame = Image.new('RGB', self.resolution, (255, 255, 255))
        draw = ImageDraw.Draw(self.frame)
        self.plot_scan(self.frame, distances, angles, self.max_dist, draw)
        return self.frame

    def shutdown(self):
        pass


class BreezySLAM(object):
    '''
    https://github.com/simondlevy/BreezySLAM
    '''
    def __init__(self, MAP_SIZE_PIXELS=500, MAP_SIZE_METERS=10):
        from breezyslam.algorithms import RMHC_SLAM
        from breezyslam.sensors import Laser

        laser_model = Laser(scan_size=360, scan_rate_hz=10., detection_angle_degrees=360, distance_no_detection_mm=12000)
        MAP_QUALITY=5
        self.slam = RMHC_SLAM(laser_model, MAP_SIZE_PIXELS, MAP_SIZE_METERS, MAP_QUALITY)
    
    def run(self, distances, angles, map_bytes):
        
        self.slam.update(distances, scan_angles_degrees=angles)
        x, y, theta = self.slam.getpos()

        if map_bytes is not None:
            self.slam.getmap(map_bytes)

        #print('x', x, 'y', y, 'theta', norm_deg(theta))
        return x, y, deg2rad(norm_deg(theta))

    def shutdown(self):
        pass



class BreezyMap(object):
    '''
    bitmap that may optionally be constructed by BreezySLAM
    '''
    def __init__(self, MAP_SIZE_PIXELS=500):
        self.mapbytes = bytearray(MAP_SIZE_PIXELS * MAP_SIZE_PIXELS)

    def run(self):
        return self.mapbytes

    def shutdown(self):
        pass

class MapToImage(object):

    def __init__(self, resolution=(500, 500)):
        self.resolution = resolution

    def run(self, map_bytes):
        np_arr = np.array(map_bytes).reshape(self.resolution)
        return arr_to_img(np_arr)

    def shutdown(self):
        pass


class Path(object):
    def __init__(self, min_dist_rec_mm = 100.):
        self.path = []
        self.min_dist = min_dist_rec_mm
        self.x = 0.
        self.y = 0.

    def run(self, x, y):
        d = dist(x, y, self.x, self.y)
        if d > self.min_dist:
            self.path.append((x, y))
            self.x = x
            self.y = y
        return self.path

    def save(self, filename):
        outfile = open(filename, 'wb')
        pickle.dump(self.path, outfile)
    
    def load(self, filename):
        infile = open(filename, 'rb')
        self.path = pickle.load(infile)

    def shutdown(self):
        pass


class CarRelPathPlotter(object):
    '''
    draw a path onto an image relative to car position.
    '''
    def __init__(self):
        pass

    def transform_path(self, x, y, theta, path, img):
        tm_path = []
        cos_th = math.cos(theta)
        sin_th = math.sin(theta)
        cx = img.width / 2
        cy = img.height / 2
        max_dist = 5000.0
        for px, py in path:
            dx = px - x
            dy = py - y
            #to car relative coordinates
            tx = dx * cos_th - dy * sin_th
            ty = dx * sin_th + dy * cos_th
            #to pixel space - assumes car in center of image
            px = tx / max_dist * cx + cx
            py = ty / max_dist * cy + cy
            tm_path.append((int(px), int(py)))

        return tm_path

    def plot_line(self, sx, sy, ex, ey, draw, color):
        '''
        scale dist so that max_dist is edge of img (mm)
        and img is PIL Image, draw the line using the draw ImageDraw object
        '''
        draw.line((sx,sy, ex, ey), fill=color, width=1)


    def run(self, x, y, theta, path, img):
        try:
            tm_path = self.transform_path(x, y, theta, path, img)
            draw = ImageDraw.Draw(img)
            color = (255, 0, 0)
            for iP in range(0, len(tm_path) - 1):
                ax, ay = tm_path[iP]
                bx, by = tm_path[iP + 1]
                self.plot_line(ax, ay, bx, by, draw, color)
        except:
            pass
        return img

    def shutdown(self):
        pass



class PathCTE(object):
    def __init__(self, path):
        self.path = path
        self.i_span = 0

    def run(self, x, y):
        cte = 0.
        closest_dist = 1000000.
        iClosest = 0
        for iPath, pos in enumerate(self.path.path):
            xp, yp = pos
            d = dist(x, y, xp, yp)
            if d < closest_dist:
                closest_dist = d
                iClosest = iPath

        #check if next or prev is closer
        iNext = (iClosest + 1) % len(self.path.path)
        iPrev = (iClosest - 1) % len(self.path.path)
        npx, npy = self.path.path[iNext]
        dist_next = dist(x, y, npx, npy)
        ppx, ppy = self.path.path[iPrev]
        dist_prev = dist(x, y, ppx, ppy)
        if dist_next < dist_prev:
            iB = iNext
        else:
            iB = iPrev

        ax, ay = self.path.path[iClosest]
        bx, by = self.path.path[iB]

        cx, cy = closest_pt_on_line(ax, ay, bx, by, x, y)


        return cte
