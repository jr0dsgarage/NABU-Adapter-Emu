#!/usr/bin/env python3
# 
# Original code: NABU Adaptor Emulator - Copyright Mike Debreceni - 2022
#       https://github.com/mdebreceni/nabu-pc-playground/
#   Source of bulk of code to load, parse and send segment data to the NABU and handle requests
#
# Major rewrite/expansion by Sark, 12/28/2022:
# 
#   Updated to work with original unmodified (but decrypted) cycle files from NABU network.
#   Added support for loading from a directory of pak files
#   Added time segment generation
#   Added checksum generation and segment checking/patching
#   Added trailing 1a detection and patching
#   Terminology fixup to update variable names, notes and messages:
#       Segment is a chunk of a program, less than 1K in size
#       Pak is a group of segments
#   Added checking/recovery for files that don't exist: when in doubt... penguins!
#   Pak files are only loaded from disk once as needed, then stored in library variable
#   Output messages trimmed and condensed
#   Pak directory selectable from command line option, but defaults available for all settings
#   Now supports loading encrypted files from Internet cloud source, such as http://cloud.nabu.ca/cycle1/

# This works with a directory of pak files, specified at command line or by default variable below
# Will work with unmodified (but decrypted) files from both cycle 1 and 2 of the original NABU network
# Filename 000001.pak is menu and is loaded to begin, the rest are uppercase hex filenames with .pak extension
# Can also be used with Internet cloud source of encrypted files, set location with switch or variable

import serial
import time
import os
import argparse

from nabu_data import NabuSegment, NabuPak

def send_ack():
    sendBytes(bytes([0x10, 0x06]))

def send_time():
##  Pre-formed time segment, sends Jan 1 1984 at 00:00:00
##    sendBytes(bytes([0x7f, 0xff, 0xff, 0x00, 0x01, 0x7f, 0xff, 0xff, 0xff, 0x7f, 0x80, 0x20, 0x00, 0x00, 0x00, 0x00, 0x02, 0x02, 0x02, 0x54, 0x01, 0x01, 0x00, 0x00, 0x00, 0xc6, 0x3a]))
    currenttime = NabuSegment()
    sendBytes(currenttime.get_time_segment())

# TODO:  We can probably get rid of handle_0xf0_request, handle_0x0f_request and handle_0x03_request
# TODO:  as these bytes may have been from RS-422 buffer overruns / other errors

def handle_0xf0_request(data):  
    sendBytes(bytes([0xe4]))

def handle_0x0f_request(data):
    sendBytes(bytes([0xe4]))

def handle_0x03_request(data):
    sendBytes(bytes([0xe4]))

def handle_reset_segment_handler(data):
    sendBytes(bytes([0x10, 0x06, 0xe4]))

def handle_reset(data):
    send_ack()

def handle_get_status(data):
    global channelCode
    send_ack()

    response = recvBytes()
    if channelCode is None:
        print("* Channel Code is not set yet.")
        # Ask NPC to set channel code
        sendBytes(bytes([0x9f, 0x10, 0xe1]))
    else:
        print("* Channel code is set to " + channelCode)
        # Report that channel code is already set
        sendBytes(bytes([0x1f, 0x10, 0xe1]))

def handle_set_status(data):
    sendBytes(bytes([0x10, 0x06, 0xe4]))

def handle_download_segment(data):
    # ; pak load request
    # [11]        NPC       $84
    #              NA        $10 06
    send_ack()
    segmentNumber=recvBytesExactLen(1)[0]
    pakNumber=bytes(reversed(recvBytesExactLen(3)))
    pakId=str(pakNumber.hex())
    print("* Requested Pak ID: " + pakId + "  * Requested Segment Number: " + str(segmentNumber))

    if pakId == "7fffff":
        print("Time packet requested")
        sendBytes(bytes([0xe4, 0x91]))
        pakId == ""
    else:
        sendBytes(bytes([0xe4, 0x91]))
        response = recvBytes(2)
        print("* Response from NPC: " + response.hex(" "))

    # Get Segment from internal segment store
        if pakId not in paks:
            print("Pak not already in memory... loading...")
            loadpak(pakId)
            sendBytes(bytes([0x91]))
        pak = paks[pakId]

                
    # Get requested segment from that pak
        segment_data = pak.get_segment(segmentNumber)

    # Dump information about segment.  'segment' is otherwise unused
        segment = NabuSegment()
        segment.ingest_bytes(segment_data)
##            print("* Segment to send: " + segment_data.hex(' ')) 
#            print("* Pak ID: "+ segment.pak_id.hex())
#            print("* Segment Number: " + segment.segmentnum.hex())
#            print("* Pak owner: " + segment.pak_owner.hex())
#            print("* Pak tier: " + segment.pak_tier.hex())
#            print("* Pak mystery_bytes: " + segment.pak_mystery_bytes.hex())
#            print("* Segment Type: " + segment.segment_type.hex())
#            print("* Segment Number: " + segment.segment_number.hex())
#            print("* Segment Offset: " + segment.segment_offset.hex())
#            print("* Segment CRC: " + segment.segment_crc.hex())
#            print("* Segment length: {}".format(len(segment_data)))

    # check checksum
        seglength= len(segment_data)
#            print(seglength)
#            print(segment_data)
        checkedpack=NabuSegment()
        sd=bytearray(segment_data)
        chk=checkedpack.add_checksum(sd[0:seglength-2])
#            print(chk[-2:].hex(' '))
#            print(bytes(chk[-2:]))
#            print(bytes(segment.segment_crc))
        if chk[-2:] == segment.segment_crc:
            print("Pak: "+segment.pak_id.hex()+"  Segment: "+segment.segmentnum.hex()+ "  Checksum: "+segment.segment_crc.hex()+"    [Checksum Valid!]")
        else:
            print("Pak: "+segment.pak_id.hex()+"  Segment: "+segment.segmentnum.hex()+ "  Checksum: "+segment.segment_crc.hex())
            print("##### Corrupt PAK file! #####  Checksum:", segment.segment_crc.hex(), "Should be:", chk[-2:].hex(), " ##### fixing...")
            segment_data = chk
                
    # escape pack data (0x10 bytes should be escaped maybe?)
        escaped_segment_data = escapeUploadBytes(segment_data)
        sendBytes(escaped_segment_data)
        sendBytes(bytes([0x10, 0xe1]))

def handle_set_channel_code(data):
    global channelCode
    send_ack()
    data = recvBytesExactLen(2)
    while len(data) < 2:
        remaining = 2 - len(data)
        print("Waiting for channel code")
        print(data.hex(' '))
        data = data + recvBytes(remaining)

    print("* Received Channel code bytes: " + data.hex())
    channelCode = bytes(reversed(data)).hex()
    print("* Channel code: " + channelCode)
    sendBytes(bytes([0xe4]))

def handle_0x8f_req(data):
    print("* 0x8f request")
    data = recvBytes()
    sendBytes(bytes([0xe4]))

def handle_unimplemented_req(data):
    print("* ??? Unimplemented request")
    print("* " + data.hex(' '))

def escapeUploadBytes(data):
    escapedBytes = bytearray()

    for idx in range(len(data)):
        byte=data[idx]
        if(byte == 0x10):
            escapedBytes.append(byte)
            escapedBytes.append(byte)
        else:
            escapedBytes.append(byte)

    return escapedBytes

def sendBytes(data):
    chunk_size=6
    index=0
    delay_secs=0
    end=len(data)

    while index + chunk_size < end:
        ser.write(data[index:index+chunk_size])
#        print("NA-->NPC:  " + data[index:index+chunk_size].hex(' '))
        index += chunk_size
        time.sleep(delay_secs)

    if index != end:
#        print("NA-->NPC:  " + data[index:end].hex(' '))
        ser.write(data[index:end])

def recvBytesExactLen(length=None):
    if(length is None):
        return None
    data = recvBytes(length)
    while len(data) < length:
        remaining = length - len(data)
#        print("Waiting for {} more bytes".format(length - len(data)))
        print(data.hex(' '))
        time.sleep(0.01)
        data = data + recvBytes(remaining)
    return data

def recvBytes(length = None):
    if(length is None):
        data = ser.read(MAX_READ)
    else:
        data = ser.read(length)
    if(len(data) > 0):
        print("NPC-->NA:   " + data.hex(' '))
    return data

# Loads pak from file, assumes file names are all upper case with a lower case .pak extension

def loadpak(filename):
    if args.internetlocation is not None:
        pak1 = NabuPak()
        paknum = int(filename,16)
        print(paknum)
        print("### Loading NABU segments into memory from "+args.internetlocation)
        pak1.get_cloud_pak(args.internetlocation, paknum)
    else:   
        file = filename.upper()
        print("* Loading NABU Segments into memory from disk")
        pak1 = NabuPak()
        if os.path.exists( args.paksource + file + ".pak") == False:
            print("Pak file does not exist... here, have some penguins instead.")
            file = "000120"
        pak1.ingest_from_file( args.paksource + file + ".pak")
    paks[filename] = pak1

######  Begin main code here
global paks
paks = {}    # Creates library variable to store loaded paks in memory

MAX_READ=65535
DEFAULT_BAUDRATE=111863
DEFAULT_SERIAL_PORT="/dev/ttyUSB0"
DEFAULT_PAK_DIRECTORY="./paks/"
CLOUD_LOCATION="http://cloud.nabu.ca/cycle1/"
#CLOUD_LOCATION=None

# channelCode = None
channelCode = '0000'



parser = argparse.ArgumentParser()
# Optional serial port selection
parser.add_argument("-t", "--ttyname",
help="Set serial device (e.g. /dev/ttyUSB0)",
default=DEFAULT_SERIAL_PORT)
# Optional baud rate selection
parser.add_argument("-b", "--baudrate",
type=int,
help="Set serial baud rate (default: {} BPS)".format(DEFAULT_BAUDRATE),
default=DEFAULT_BAUDRATE)
# Optional pak directory selection
parser.add_argument("-p", "--paksource",
help="Set location of the pak files (default: {} )".format(DEFAULT_PAK_DIRECTORY),
default=DEFAULT_PAK_DIRECTORY) 
# Optional pak Internet location selection
parser.add_argument("-i", "--internetlocation",
help="Set Internet location to source pak files, if not specified, load from disk",
default=CLOUD_LOCATION)
		
args = parser.parse_args()

loadpak("000001")

# Some hard-coded things here (timeout, stopbits)
ser = serial.Serial(port=args.ttyname, baudrate=args.baudrate, timeout=0.5, stopbits=serial.STOPBITS_TWO)


# Some hard-coded things here. 
#ser = serial.Serial(port='/dev/ttyUSB0', baudrate=111865, timeout=0.5, stopbits=serial.STOPBITS_TWO)

while True:
    data = recvBytes()
    if len(data) > 0:
        req_type = data[0]

        if req_type == 0x03:
            print("* 0x03 request")
            handle_0x03_request(data)
        elif req_type == 0x0f:
            print("* 0x0f request")
            handle_0x0f_request(data)
        elif req_type == 0xf0:
            print("* 0xf0 request")
            handle_0xf0_request(data)
        elif req_type == 0x80:
            print("* Reset segment handler")
            handle_reset_segment_handler(data)
        elif req_type == 0x81:
            print("* Reset")
            handle_reset(data)
        elif req_type == 0x82:
            print("* Get Status")
            handle_get_status(data)
        elif req_type == 0x83:
            print("* Set Status")
            handle_set_status(data)
        elif req_type == 0x84:
            print("* Download Segment Request")
            handle_download_segment(data)
        elif req_type == 0x85:
            print("* Set Channel Code")
            handle_set_channel_code(data)
            print("* Channel code is now " + channelCode)
        elif req_type == 0x8f:
            print("* Handle 0x8f")
            handle_0x8f_req(data)
        elif req_type == 0x10:
            print("got request type 10, sending time")
            send_time()
            sendBytes(bytes([0x10, 0xe1]))

        else:
            print("* Req type {} is Unimplemented :(".format(data[0]))
            handle_unimplemented_req(data)

