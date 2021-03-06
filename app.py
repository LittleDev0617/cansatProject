#!/usr/bin/env python
from importlib import import_module
from logging import NOTSET
import os
from flask import Flask, render_template, Response, request, session, redirect, send_file
from flask.helpers import url_for
from flask_socketio import SocketIO, send, emit
import time, threading, json
from datetime import datetime
import socket

import os
logFilePath = '/home/pi/dataLog.csv'

hostname = socket.gethostname()
import sqlite3 as sql
conn = sql.connect('/home/pi/cansat-gs/cansat.db',check_same_thread=False)
conn.row_factory = sql.Row
# bmp280 sensor
import board
# import digitalio # For use with SPI
import busio
import adafruit_bmp280

import Adafruit_BMP.BMP085 as BMP085
bmp180 = BMP085.BMP085()

# Create library object using our Bus I2C port
# i2c = busio.I2C(board.SCL, board.SDA)
# bmp280 = adafruit_bmp280.Adafruit_BMP280_I2C(i2c)

# change this to match the location's pressure (hPa) at sea level
# bmp280.sea_level_pressure = 1013.25

# import camera driver
if os.environ.get('CAMERA'):
    Camera = import_module('camera_' + os.environ['CAMERA']).Camera
else:
    from camera_pi import Camera

# import for virtual sensing values
import random

# save threads in list for each client session
users = []
logger = None
startTime = datetime.now()

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
app.config['TEMPLATES_AUTO_RELOAD'] = True
 # only camera lib works threading mode with socketio
socketio = SocketIO(app, async_mode="threading")

isRecording = False

def strfdelta(tdelta):
    d = {"D": tdelta.days}
    hours, rem = divmod(tdelta.seconds, 3600)
    minutes, seconds = divmod(rem, 60)
    return '{:02}:{:02}:{:02}'.format(int(hours), int(minutes), int(seconds))

# get current local time
def updateTime():
    now = datetime.now()
    current_time = now.strftime("%H:%M:%S")
    socketio.emit('updateTime', current_time)

    elepsed = now - startTime
    #print(str(elepsed))
    running_time = strfdelta(elepsed)
    #print(running_time)
    socketio.emit('runningTime', running_time)

# get sensing value
def updateSensVal():
    temp = bmp180.read_temperature()
    pressure = bmp180.read_pressure() / 100 # convert Pa to hPa
    altitude = bmp180.read_altitude()

    #temp = bmp280.temperature
    #pressure = bmp280.pressure
    #altitude = bmp280.altitude

    sensVal = {
        'temp' : temp,
        'pressure' : pressure,
        'altitude' : altitude
    }
    socketio.emit('updateSensVal', json.dumps(sensVal))

class userTask(threading.Thread):
    def __init__(self, name, callback, sleep):
        super().__init__()
        self._kill = threading.Event()
        self._sleep = sleep
        self._callback = callback
        self.name = name

    def run(self):
        print(self.name + ' thread starts')
        while True:
            self._callback()
            time.sleep(self._sleep) #sleep during x seconds

            # If no kill signal is set, sleep for the interval,
            # If kill signal comes in while sleeping, immediately
            #  wake up and handle
            is_killed = self._kill.wait(0)
            if is_killed:
                break

        # print(self.name + ' thread killed')

    def kill(self):
        self._kill.set()

# socketio data binding implementation
@socketio.on('connect')
def connect():
    print(request.remote_addr + ' Connected')

    # threading updateTime()
    th1 = userTask(name = 'updateTime', callback = updateTime, sleep = 1)
    th2 = userTask(name = 'updateSensVal', callback = updateSensVal, sleep = 0.2)

    user = {
        'addr' : request.remote_addr,
        'threads' : [ th1, th2]
    }

    users.append(user)

    # starts threads
    for th in user['threads']:
        th.daemon = True
        th.start()

@socketio.on('disconnect')
def disconnect():
    print(request.remote_addr + ' Disconnected')
    #session.clear()

    idx = next((index for (index, item) in enumerate(users) if item['addr'] == request.remote_addr), None)
    user = users[idx]
    
    for th in user['threads']:
        th.kill()

    del users[idx]

# camera frame generator
def gen(camera):
    """Video streaming generator function."""
    while True:
        frame = camera.get_frame()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

class Logger(threading.Thread):
    def __init__(self,name,logfileName,sleep):
        super().__init__()
        self.name = name
        self.logfileName = logfileName
        self.sleep = sleep
    
    def run(self):
        global isRecording
        while True:
            if isRecording:
                if not os.path.isfile(self.logfileName):
                    with open(self.logfileName,'w') as f:
                        f.write('Date,Temperature,Pressure,Altitude\n')
                else:
                    with open(self.logfileName,'a') as f:
                        temp = bmp180.read_temperature()
                        pressure = bmp180.read_pressure() / 100
                        altitude = bmp180.read_altitude()
                        f.write('%s,%d,%d,%d\n' % (datetime.now().strftime('%Y-%m-%d %H:%M:%S'),temp,pressure,altitude))
            else:
                break
            time.sleep(self.sleep)

@app.route('/video_feed')
def video_feed():
    if not 'userName' in session:       
       return redirect(url_for('login'))

    """Video streaming route. Put this in the src attribute of an img tag."""
    return Response(gen(Camera()),
                    mimetype='multipart/x-mixed-replace; boundary=frame')

# html routes
@app.route('/')
def index():
    global isRecording
    print(session)
    if 'userName' in session:
        return render_template('index.html', hostname="LittleDev0617",isRecording=isRecording)
    else:
       return redirect(url_for('login'))


@app.route('/dataRecord')
def dataRecord():
    if not 'userName' in session:       
       return redirect(url_for('login'))

    global isRecording
    global logger
    global logFilePath

    isRecording = not isRecording
    if isRecording:
        logger = Logger('logger', logFilePath,5)
        logger.start()
    else:
        logger.join()
    return json.dumps({'isRecording' : isRecording})

@app.route('/dataRecordState')
def dataRecordState():
    if not 'userName' in session:       
       return redirect(url_for('login'))
    global isRecording
    return json.dumps({'isRecording' : isRecording})

@app.route('/logFile')
def logFile():
    if not 'userName' in session:       
       return redirect(url_for('login'))

    with open(logFilePath,'r') as f:
        return '<br />'.join(f.readlines())

@app.route('/login', methods = ['GET','POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')
    elif request.method == 'POST':
        userName = request.form.get('userName')
        userPw = request.form.get('userPw')
        print(userName)
        print(userPw)
        cur = conn.cursor() 
        cur.execute('select * from users where userName=? and userPw=?',(userName,userPw))
        r = cur.fetchall()
        print(r)
        cur.close()
        for user in r:
            print(user)
            if user['userName'] == 'admin':
                session['userName'] = 'admin'
                return redirect(url_for('index'))
        return redirect(url_for('login'))

@app.route('/logout')
def logout():
    session.pop('userName',None)
    return redirect(url_for('index'))


# starts socketio server
if __name__ == '__main__':

    socketio.run(app, host='0.0.0.0')
