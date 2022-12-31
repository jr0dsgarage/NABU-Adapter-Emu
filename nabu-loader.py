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
import platform
import logging

from nabu_data import NabuSegment, NabuPak

DEFAULT_LOG_LEVEL = logging.WARNING

MAX_READ = 65535
DEFAULT_BAUDRATE = 111863

DEFAULT_PAK_DIRECTORY = "./paks/"
DEFAULT_PAK_NAME = "000001"
CLOUD_LOCATION = "http://cloud.nabu.ca/cycle1/"
# CLOUD_LOCATION=None

match platform.system():
    case "Linux":
        DEFAULT_SERIAL_PORT = "/dev/ttyUSB0"
    case "Windows":
        DEFAULT_SERIAL_PORT = "COM3"

request_handlers = {
    0x03: '* 0x03 request',
    0x0f: '* 0x0f request',
    0xf0: '* 0xf0 request',
    0x80: '* Reset segment handler',
    0x81: '* Reset',
    0x82: '* Get Status',
    0x83: '* Set Status',
    0x84: '* Download Segment Request',
    0x85: '* Set Channel Code',
    0x8f: '* Handle 0x8f',
    0x10: '* Request type 10> Sending Time',
}


def send_ack(serial_connection):
    sendBytes(serial_connection, bytes([0x10, 0x06]))


def send_time(serial_connection):
    """ Pre-formed time segment, sends Jan 1 1984 at 00:00:00
     sendBytes(bytes([0x7f, 0xff, 0xff, 0x00, 0x01, 0x7f, 0xff, 0xff, 0xff, 0x7f, 0x80, 0x20, 0x00, 0x00,
                        0x00, 0x00,0x02, 0x02, 0x02, 0x54, 0x01, 0x01, 0x00, 0x00, 0x00, 0xc6, 0x3a]))"""
    currenttime = NabuSegment()
    sendBytes(serial_connection, currenttime.get_time_segment())
    logging.info('Sent Time as {}'.format(currenttime.get_time_segment()))

# TODO:  We can probably get rid of handle_0xf0_request, handle_0x0f_request and handle_0x03_request
# TODO:  as these bytes may have been from RS-422 buffer overruns / other errors


def handle_request(serial_connection, args, data, paks, channelCode):
    logging.info("Handling Request: {}".format(request_handlers[data[0]]))
    match data[0]:
        case 0xf0, 0x0f, 0x03:
            sendBytes(serial_connection, bytes([0xe4]))
        case 0x10:  # send time
            logging.info("Request type 10, sending Time")
            send_time(serial_connection)
            sendBytes(serial_connection, bytes([0x10, 0xe1]))
        case 0x80:  # reset segment
            sendBytes(serial_connection, bytes([0x10, 0x06, 0xe4]))
        case 0x81:  # Reset
            send_ack(serial_connection)
        case 0x82:  # Get Status
            send_ack(serial_connection)
            response = receiveBytes(serial_connection)
            if channelCode is None:  # Ask NABUPC to set channel code
                logging.warning("* Channel Code is not set yet.")
                sendBytes(serial_connection, bytes([0x9f, 0x10, 0xe1]))
            else:  # Report that channel code is already set
                logging.info("* Channel code is set to {}".format(channelCode))
                sendBytes(serial_connection, bytes([0x1f, 0x10, 0xe1]))
        case 0x83:  # Set Status
            sendBytes(serial_connection, bytes([0x10, 0x06, 0xe4]))
        case 0x84:  # Download Segment Request
            # ; pak load request
            # [11]        NPC       $84
            #              NA        $10 06
            send_ack(serial_connection)
            segmentNumber = recvBytesExactLen(serial_connection, 1)[0]
            pakNumber = bytes(
                reversed(recvBytesExactLen(serial_connection, 3)))
            pakId = str(pakNumber.hex())
            logging.info("* Requested Pak ID: {} * Requested Segment Number: {}".format(pakId, segmentNumber))

            if pakId == "7fffff":
                logging.info("Time packet requested")
                sendBytes(serial_connection, bytes([0xe4, 0x91]))
                pakId == ""
            else:
                sendBytes(serial_connection, bytes([0xe4, 0x91]))
                response = receiveBytes(serial_connection, 2)
                logging.info("* Response from NPC: {}".format(response.hex(" ")))
                if pakId not in paks:  # Get Segment from internal segment store
                    logging.warning("Pak not already in memory... loading...")
                    loadpak(pakId, args, paks)
                    sendBytes(serial_connection, bytes([0x91]))
                pak = paks[pakId]

            # Get requested segment from that pak
                segment_data = pak.get_segment(segmentNumber)

            # Dump information about segment.  'segment' is otherwise unused
                segment = NabuSegment()
                segment.ingest_bytes(segment_data)
                """
                print("* Segment to send: " + segment_data.hex(' '))
                print("* Pak ID: "+ segment.pak_id.hex())
                print("* Segment Number: " + segment.segmentnum.hex())
                print("* Pak owner: " + segment.pak_owner.hex())
                print("* Pak tier: " + segment.pak_tier.hex())
                print("* Pak mystery_bytes: " + segment.pak_mystery_bytes.hex())
                print("* Segment Type: " + segment.segment_type.hex())
                print("* Segment Number: " + segment.segment_number.hex())
                print("* Segment Offset: " + segment.segment_offset.hex())
                print("* Segment CRC: " + segment.segment_crc.hex())
                print("* Segment length: {}".format(len(segment_data))) 
                """

                # check checksum
                seglength = len(segment_data)
                # print(seglength)
                # print(segment_data)
                checkedpack = NabuSegment()
                sd = bytearray(segment_data)
                chk = checkedpack.add_checksum(sd[0:seglength-2])
                """ 
                print(chk[-2:].hex(' '))
                print(bytes(chk[-2:]))
                print(bytes(segment.segment_crc)) 
                """
                if chk[-2:] == segment.segment_crc:
                    print("Pak: {} Segment: {}  Checksum: {}  [Checksum Valid!]".format(
                        segment.pak_id.hex(), segment.segmentnum.hex(), segment.segment_crc.hex()))
                else:
                    logging.info("Pak: {}  Segment: {}  Checksum: {}".format(
                        segment.pak_id.hex(), segment.segmentnum.hex(), segment.segment_crc.hex()))
                    logging.error("##### Corrupt PAK file! #####  Checksum: {} Should be: {} ##### fixing...".format(
                        segment.segment_crc.hex(), chk[-2:].hex()))
                    segment_data = chk

                # escape pack data (0x10 bytes should be escaped maybe?)
                escaped_segment_data = escapeUploadBytes(segment_data)
                sendBytes(serial_connection, escaped_segment_data)
                sendBytes(serial_connection, bytes([0x10, 0xe1]))
        case 0x85:  # Set Channel Code
            send_ack(serial_connection,)
            data = recvBytesExactLen(2)
            while len(data) < 2:
                remaining = 2 - len(data)
                print("Waiting for channel code...")
                logging.debug(data.hex(' '))
                data = data + receiveBytes(remaining)

            logging.info("* Received Channel code bytes: {}".format(data.hex()))
            channelCode = bytes(reversed(data)).hex()
            logging.info("* Channel code: {}".format(channelCode))
            sendBytes(serial_connection, bytes([0xe4]))
        case 0x8f:
            logging.info("* 0x8f request")
            data = receiveBytes(serial_connection)
            sendBytes(serial_connection, bytes([0xe4]))
        case _:  # default case
            logging.warning("* ??? Unimplemented request")
            logging.warning("* {}".format(data.hex(' ')))


def escapeUploadBytes(data):
    escapedBytes = bytearray()
    for idx in range(len(data)):
        byte = data[idx]
        if (byte == 0x10):
            escapedBytes.append(byte)
            escapedBytes.append(byte)
        else:
            escapedBytes.append(byte)
    return escapedBytes


def sendBytes(serial_connection, data):
    chunk_size = 6
    index = 0
    delay_secs = 0
    end = len(data)

    while index + chunk_size < end:
        serial_connection.write(data[index:index+chunk_size])
        logging.info("NA-->NPC:  " + data[index:index+chunk_size].hex(' '))
        index += chunk_size
        time.sleep(delay_secs)

    if index != end:
        # print("NA-->NPC:  " + data[index:end].hex(' '))
        serial_connection.write(data[index:end])


def recvBytesExactLen(serial_connection, length=None):
    if (length is None):
        return None
    data = receiveBytes(serial_connection, length)
    while len(data) < length:
        remaining = length - len(data)
#        print("Waiting for {} more bytes".format(length - len(data)))
        print(data.hex(' '))
        time.sleep(0.01)
        data = data + receiveBytes(serial_connection, remaining)
    return data


def receiveBytes(serial_connection, length=None):
    if (length is None):
        received_data = serial_connection.read(MAX_READ)
    else:
        received_data = serial_connection.read(length)
    if (len(received_data) > 0):
        logging.info("NPC-->NA:   {}".format(received_data.hex(' ')))
    return received_data


def loadpak(filename, args, paks): # Loads pak from file, assumes file names are all upper case with a lower case .pak extension
    if args.internetlocation:
        pak1 = NabuPak()
        print("### Loading NABU segments into memory from {}".format(args.internetlocation))
        pak1.get_cloud_pak(args.internetlocation, int(filename, 16))
    else:
        file = filename.upper()
        print("### Loading NABU Segments into memory from disk")
        pak1 = NabuPak()
        if not os.path.exists("{}{}.pak".format(args.paksource,file)):
            logging.error("Pak file does not exist... here, have some penguins instead.")
        pak1.ingest_from_file("{}{}.pak".format(args.paksource,file))
    paks[filename] = pak1


def get_args(parser):
    parser.add_argument("-t", "--ttyname",
                        help="Set serial device (e.g. /dev/ttyUSB0 or COM3)",
                        default=DEFAULT_SERIAL_PORT)
    parser.add_argument("-b", "--baudrate",
                        type=int,
                        help="Set serial baud rate (default: {} BPS)".format(DEFAULT_BAUDRATE),
                        default=DEFAULT_BAUDRATE)
    parser.add_argument("-p", "--paksource",
                        help="Set location of the pak files (default: {} )".format(DEFAULT_PAK_DIRECTORY),
                        default=DEFAULT_PAK_DIRECTORY)
    parser.add_argument("-i", "--internetlocation",
                        help="Set Internet location to source pak files, if not specified, load from disk",
                        default=CLOUD_LOCATION)
    parser.add_argument("-l", "--log",
                        help="Choose a level of Log output [DEBUG,INFO,WARNING,ERROR,CRITICAL]. (default: {} )".format(DEFAULT_LOG_LEVEL),
                        default=DEFAULT_LOG_LEVEL)
    return parser.parse_args()


def main(args):
    if args.log:
        logging.basicConfig(level=args.log)
        logging.info("Logging using level: {}".format(logging.getLevelName(args.log)))

    channelCode = '0000'
    loaded_paks = {}
    loadpak(DEFAULT_PAK_NAME, args, loaded_paks)
    try:
        serial_connection = serial.Serial(
            port=args.ttyname,
            baudrate=args.baudrate,
            timeout=0.5,
            stopbits=serial.STOPBITS_TWO)
    except serial.SerialException as err:
        logging.error(err)

    while True:
        data = receiveBytes(serial_connection)
        if data:
            handle_request(serial_connection, args, data, loaded_paks, channelCode)


if __name__ == "__main__":
    args = get_args(argparse.ArgumentParser())
    main(args)
