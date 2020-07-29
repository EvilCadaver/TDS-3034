import serial
import sys
import os
import serial.tools.list_ports as list_ports
import math
import csv
from datetime import datetime
from pathlib import Path
import argparse
import numpy as np
from scipy.signal import savgol_filter
import matplotlib.pyplot as plt

## Constants
smooth_window = 11 # must be odd 
smooth_order = 2 # must be smaller then smoothing window

##  Command-line parsing options
parser = argparse.ArgumentParser(description='Data acquisition from Tektronix TDS 3034')
parser.add_argument('COM port', metavar= 'COM#',  type=str, help='specify the serical communication port, e.g. COM3')
parser.add_argument('-c', '--channels', dest='channels', type=str, help='specify channels to read data from, e.g. "-c 134" or "--channels 24" (default == 12)')
parser.add_argument('-s', '--smooth', dest='smooth', action='store_true', help='smoothen the data (default == False)')
parser.add_argument('-d', '--directory', dest='save_path', type=str, help='specify the path to the directory where to save the data (default == "execution directory"); use quote mark if the name has spaces')

##  Parsing command-line arguments
args = parser.parse_args()

COMport = getattr(args, 'COM port')
smoothing = args.smooth

if (save_path := args.save_path) == None:
    save_path = '.'
elif not os.path.exists(save_path):
    os.makedirs(save_path)

ACQ_CH = list()

if (channels := args.channels) == None:
    channels = '12'

for i in range(1,5):
    if (channels.find(str(i)) >= 0):
        ACQ_CH.append(i)

# Setting up serial communication parameters
ser = serial.Serial()
ser.baudrate = 38400
ser.port = COMport
ser.rtscts = True
ser.timeout = 30

# Checking the selected port for existence
myports = [tuple(p) for p in list(list_ports.comports())]
port_exists = False
for port in myports:
    if port[0] == ser.port:
        port_exists = True
if not port_exists:
    print("Selected port doesn't exist!")
    print('Choose from existing:')
    print(myports)
    sys.exit()

# Opening selected serial port
ser.open()
if not ser.is_open:
    print('Cannot open ' + ser.port + ' serial port. Exiting...')
    sys.exit()

# Requesting device identification
ser.write(b'*CLS\n')
ser.write(b'*IDN?\n')
print('Identification: ' + (IDN:=str(ser.readline(), 'utf-8')[:-1]))
if not IDN == "TEKTRONIX,TDS 3034,0,CF:91.1CT FV:v3.29 TDS3GM:v1.00 TDS3FFT:v1.00 TDS3TRG:v1.00":
    print("Device connected to ", COMport, " is not the TEKTRONIX,TDS 3034,0,CF:91.1CT FV:v3.29 TDS3GM:v1.00 TDS3FFT:v1.00 TDS3TRG:v1.00.")
    sys.exit()
    
# Current timestamp
print(now := str(datetime.now()).split('.')[0])

# Setting up the data format and time precision
ser.write(b'WFMPre:BIT_Nr 16\n')
ser.write(b'WFMPre:BIT_Nr?\n')
print('Number of bits per point: ' + str(ser.readline(), 'utf-8')[:-1])
ser.write(b'DATa:WIDth?\n')
print('Data width in bytes: ' + str(ser.readline(), 'utf-8')[:-1])
ser.write(b'WFMPre:ENCdg ASC\n')
ser.write(b'WFMPre:ENCdg?\n')
print('Data encoding: ' + str(ser.readline(), 'utf-8')[:-1])

# ser.write(b'HORizontal:RECOrdlength 10000\n')
ser.write(b'HORizontal?\n')
print('HORizontal settings: ' + str(ser.readline(), 'utf-8')[:-1])

# Definition of the data acquisition limits
ser.write(b'DATa:STARt 1\n')
ser.write(b'DATa:STARt?\n')
print('Data start: ' + str(ser.readline(), 'utf-8')[:-1])
ser.write(b'DATa:STOP 10000\n')
ser.write(b'DATa:STOP?\n')
print('Data stop: ' + str(ser.readline(), 'utf-8')[:-1])

plt.figure()
plt.suptitle('Acquired data')


for CH_number in ACQ_CH:
    # Choosing the data source
    ser.write(b'DATa:SOU CH' + bytes(str(CH_number), 'ascii') + b'\n')
    ser.write(b'DATa:SOU?\n')
    print('Data source: ' + (dat_sou := str(ser.readline(), 'utf-8')[:-1]))

    # Chossing the output filename
    filename = now + " " + dat_sou + ".csv"
    filename = filename.replace(':','-')
    filename = os.path.join(save_path, filename)

    # Reading active channel configuration
    ser.write(b'WFMPre?\n')
    ch_conf = (str(ser.readline(), 'utf-8')[:-1]).split(';')
    print('WFID = ' + (WFID := ch_conf[6]))
    print('XUNIT = ' + (XUNIT := ch_conf[11]))
    print('XINCRement = ' + str(XINCRement := float(ch_conf[8])))
    print('XZERO = ' + str(XZERO := float(ch_conf[10])))
    print('YUNIT = ' + (YUNIT := ch_conf[15]))
    print('YMULTiplier = ' + str(YMULTiplier := float(ch_conf[12])) + YUNIT)
    print('YZERO (Offset) = ' + str(YZERO := float(ch_conf[13])) + YUNIT)
    print('YOFF (Position) = ' + str(YOFF := float(ch_conf[14])*YMULTiplier) + YUNIT)

    # Data acqusition
    ser.write(b'CURVe?\n')
    ch_data_Y = np.array([float(d)*YMULTiplier for d in (str(ser.readline(), 'utf-8')[:-1]).split(',')])
    ch_data_X = np.array([round(float(x)*XINCRement + XZERO, 15) for x in range(len(ch_data_Y))])
    
    
    # Smoothing settings
    if smoothing:
        ch_data_Y_smooth = savgol_filter(ch_data_Y, smooth_window, smooth_order)
        plt.scatter(ch_data_X, ch_data_Y, s=1)
        plt.plot(ch_data_X, ch_data_Y_smooth, linewidth=1.5)
    else:
        plt.plot(ch_data_X, ch_data_Y, linewidth=1.5)
    
    # Removing offset from the data
    ch_data_Y = np.round(ch_data_Y - YOFF, 15)
    
    # Writing data to the file
    with open(filename, 'w', newline='') as csvfile:
        datawriter = csv.writer(csvfile, dialect='excel')
        datawriter.writerow([ch_conf])
        if smoothing:
            datawriter.writerow(['Time, ' + XUNIT, 'Voltage, ' + YUNIT, 'Smoothed Voltage, ' + YUNIT])
            for x, y, y_s in zip(ch_data_X, ch_data_Y, ch_data_Y_smooth):
                datawriter.writerow([x, y, y_s])
        else:
            datawriter.writerow(['Time, ' + XUNIT, 'Voltage, ' + YUNIT])
            for x, y in zip(ch_data_X, ch_data_Y):
                datawriter.writerow([x, y])

plt.show()

ser.close()