#!/usr/bin/env python3
"""
# Original code: NABU Adaptor Emulator - Copyright Mike Debreceni - 2022
#       https://github.com/mdebreceni/nabu-pc-playground/
#   Source of bulk of code to load, parse and send segment data to the NABU and handle requests
 This works with a directory of pak files, specified at command line or by default variable below
 Will work with unmodified (but decrypted) files from both cycle 1 and 2 of the original NABU network
 Filename 000001.pak is menu and is loaded to begin, the rest are uppercase hex filenames with .pak extension
 Can also be used with Internet cloud source of encrypted files, set location with switch or variable
"""
import serial
import time
import os
import argparse
import platform
from logger import logging

from nabu_data import NabuSegment, NabuPak

MAX_READ = 65535
DEFAULT_BAUDRATE = 115200 #111863

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
    0x03: '[0x03] -unknown',
    0x0f: '[0x0f] -unknown',
    0xf0: '[0xf0] -unknown',
    0x10: '[0x10] Sending Time',
    0x80: '[0x80] Reset Segment Handler',
    0x81: '[0x81] Reset',
    0x82: '[0x82] Get Status',
    0x83: '[0x83] Set Status',
    0x84: '[0x84] Download Segment Request',
    0x85: '[0x85] Set Channel Code',
    0x8f: '[0x8f] -unknoen',
}


def send_ack(serial_connection):
    sendBytes(serial_connection, bytes([0x10, 0x06]))


def send_time(serial_connection):
    """ Pre-formed time segment, sends Jan 1 1984 at 00:00:00
     sendBytes(bytes([0x7f, 0xff, 0xff, 0x00, 0x01, 0x7f, 0xff, 0xff, 0xff, 0x7f, 0x80, 0x20, 0x00, 0x00,
                        0x00, 0x00,0x02, 0x02, 0x02, 0x54, 0x01, 0x01, 0x00, 0x00, 0x00, 0xc6, 0x3a]))"""
    currenttime = NabuSegment()
    sendBytes(serial_connection, currenttime.get_time_segment())
    logging.debug('Sent Time as {}'.format(currenttime.get_time_segment().hex(' ')))

# TODO:  We can probably get rid of handle_0xf0_request, handle_0x0f_request and handle_0x03_request
# TODO:  as these bytes may have been from RS-422 buffer overruns / other errors


def handle_request(serial_connection, args, data, paks, channelCode):
    logging.info("Handling Request: {}".format(request_handlers[data[0]]))
    match data[0]:
        case 0xf0, 0x0f, 0x03:
            sendBytes(serial_connection, bytes([0xe4]))
        case 0x10:  # send time
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
                logging.warning("Channel Code is not set yet.")
                sendBytes(serial_connection, bytes([0x9f, 0x10, 0xe1]))
            else:  # Report that channel code is already set
                logging.info("Channel code is set to {}".format(channelCode))
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
            logging.debug("Requested Pak ID: {} Requested Segment Number: {}".format(pakId, segmentNumber))

            if pakId == "7fffff": # time packet id should be defined as constant
                sendBytes(serial_connection, bytes([0xe4, 0x91]))
                pakId == ""
            else:
                sendBytes(serial_connection, bytes([0xe4, 0x91]))
                response = receiveBytes(serial_connection, 2)
                logging.debug("Response from NPC: {}".format(response.hex(" ")))
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
                """ Segment ingest debug logging
                logging.debug("Ingest: Segment to send: " + segment_data.hex(' '))
                logging.debug("Ingest: Pak ID: "+ segment.pak_id.hex())
                logging.debug("Ingest: Segment Number: " + segment.segmentnum.hex())
                logging.debug("Ingest: Pak owner: " + segment.pak_owner.hex())
                logging.debug("Ingest: Pak tier: " + segment.pak_tier.hex())
                logging.debug("Ingest: Pak mystery_bytes: " + segment.pak_mystery_bytes.hex())
                logging.debug("Ingest: Segment Type: " + segment.segment_type.hex())
                logging.debug("Ingest: Segment Number: " + segment.segment_number.hex())
                logging.debug("Ingest: Segment Offset: " + segment.segment_offset.hex())
                logging.debug("Ingest: Segment CRC: " + segment.segment_crc.hex())
                logging.debug("Ingest: Segment length: {}".format(len(segment_data))) 
                """

                # check checksum
                seglength = len(segment_data)
                # print(seglength)
                # print(segment_data)
                checkedpack = NabuSegment()
                sd = bytearray(segment_data)
                chk = checkedpack.add_checksum(sd[0:seglength-2])
                if chk[-2:] == segment.segment_crc:
                    logging.debug("Pak: [{}] Segment: [{}]  Checksum: [{}]  [Checksum Valid!]".format(
                        segment.pak_id.hex(), segment.segmentnum.hex(), segment.segment_crc.hex()))
                else:
                    logging.debug("Pak: [{}]  Segment: [{}]  Checksum: [{}]".format(
                        segment.pak_id.hex(), segment.segmentnum.hex(), segment.segment_crc.hex()))
                    logging.error("##### Corrupt PAK file! #####  Checksum: [{}] Should be: [{}] fixing...".format(
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
                logging.info("# Waiting for channel code...")
                logging.debug(data.hex(' '))
                data = data + receiveBytes(remaining)

            logging.debug("Received Channel code bytes: {}".format(data.hex()))
            channelCode = bytes(reversed(data)).hex()
            logging.debug("Channel code: {}".format(channelCode))
            sendBytes(serial_connection, bytes([0xe4]))
        case 0x8f:
            data = receiveBytes(serial_connection)
            sendBytes(serial_connection, bytes([0xe4]))
        case _:  # default case
            logging.warning("[{}] - Unimplemented request".format(data.hex(' ')))


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
    chunk_size = 64
    index = 0
    #delay_secs = 0
    end = len(data)

    while index + chunk_size < end:
        serial_connection.write(data[index:index+chunk_size])
        logging.debug("NA-->NPC:[{}]".format(data[index:index+chunk_size].hex(' ')))
        index += chunk_size
        #time.sleep(delay_secs)

    if index != end:
        # print("NA-->NPC:  " + data[index:end].hex(' '))
        serial_connection.write(data[index:end])


def recvBytesExactLen(serial_connection, length=None):
    if (length is None):
        return None
    data = receiveBytes(serial_connection, length)
    while len(data) < length:
        remaining = length - len(data)
        #print("Waiting for {} more bytes".format(length - len(data)))
        #print(data.hex(' '))
        #time.sleep(0.01)
        data = data + receiveBytes(serial_connection, remaining)
    return data


def receiveBytes(serial_connection, length=None):
    if (length is None):
        received_data = serial_connection.read(MAX_READ)
    else:
        received_data = serial_connection.read(length)
    if (len(received_data) > 0):
        logging.debug("NPC-->NA:[{}]".format(received_data.hex(' ')))
    return received_data


def loadpak(filename, args, paks): # Loads pak from file, assumes file names are all upper case with a lower case .pak extension
    if args.internetlocation:
        pak1 = NabuPak()
        logging.info("Loading NABU segments into memory from {}".format(args.internetlocation))
        pak1.get_cloud_pak(args.internetlocation, int(filename, 16))
        logging.info('Loading Complete!')
    else:
        file = filename.upper()
        print("Loading NABU Segments into memory from disk")
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
    parser.add_argument("-n", "--nabufile",
                        help="Packetize and send raw .nabu file",
                        default=None)
    parser.add_argument("-l", "--log_level",
                        help="Choose a level of Log output [DEBUG,INFO,WARNING,ERROR,CRITICAL].")
    
    return parser.parse_args()


def main(args):
    if args.log_level:
        logging.getLogger().setLevel(level=args.log_level)
        logging.info("Logging using level: {}".format(logging.getLogger().getEffectiveLevel))

    channelCode = '0000'
    loaded_paks = {}

    if args.nabufile is not None:
        if not os.path.exists( args.paksource ):
            logging.error(f"No such file {args.nabufile}   END OF LINE")
        else:
            logging.info(f"Loading .nabu file ", args.nabufile, " from disk")
            pak1 = NabuPak()
            pak1.pakify_nabu_file( args.nabufile )
        loaded_paks["000001"] = pak1
    else:
        logging.info("No .nabu file specified.  ")
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
