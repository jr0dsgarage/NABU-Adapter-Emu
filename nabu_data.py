#!/usr/bin/env python3
#
# Original code: NABU Adaptor Emulator - Copyright Mike Debreceni - 2022
#       https://github.com/mdebreceni/nabu-pc-playground/
#
# Expanded and modified by Sark, 12/28/2022
#   Terminology fixup to update variable names, notes and messages to match other conventions:
#       Segment is a chunk of a program, less than 1K in size
#       Pak is a group of segments
#   Added CRC generation and time segment creation to NabuSegment class
#
#
# A NABU program (called a pak) is a single file of concatenated binaries called segments:
#
# pak
#         +-----------+-----------+-----------+-----------+
#         | segment 0 | segment 1 | segment...| segment n |
#         +-----------+-----------+-----------+-----------+
#
# Each segment is no more than 1KB and has this structure
#
# pack
#         +----------------+
#         | header 18 bytes|
#         +----------------+
#         | code =<1004    |
#         | bytes          |
#         +----------------+
#         | CRC  2 bytes   |
#         +----------------+
#
# The meaning of header bytes is as follows:
#         bytes 0,1:     segment length (excluding the header and CRC bytes, lsb first)
#         bytes 2,3,4:   pak id (msb firs)
#         byte 5:        segment id (with the first id = 0)
#         byte 6:        pak owner (the same for all PAKs; in YUNN segment owner=1)
#         bytes 7-10:    pak tier  (the same for all PAKs; in YUNN, tier= $08 $00 $00 $02)
#         bytes 11,12:   mystery bytes (the same for all PAKs; in YUNN, these bytes are $80 $19)
#         byte  13:      segment type
#         byte  14,15:   segment number (the same as byte 5)
#         byte  16,17:   offset -- pointer to the beginning of the segment from the beginning of the pak
#

import datetime
import hashlib
import requests

from logger import logging

from io import BytesIO

from Crypto.Cipher import DES
from Crypto.Util import Padding


class NabuPak:
    def __init__(self):
        self.segments = {}

    def load_segment(self, segment_bytes, segment_id):
        self.segments[segment_id] = segment_bytes

    def get_segment(self, segment_id):
        if segment_id in self.segments:
            logging.info("* Segment Found: {}".format(segment_id))
            return self.segments[segment_id]
        else:
            logging.warning("* Segment Not Found: {}".format(segment_id))
            return None

    def get_segment_count(self):
        return len(self.segments)

    def parse_pak(self, pak_bytes):
        index = 0
        junkbytes = 0
        endflag = len(pak_bytes) - 1
        while pak_bytes[endflag] == 0x1a:
            endflag = endflag - 1
            junkbytes = junkbytes + 1
        if junkbytes != 0:
            logging.warning(" Found {} extra 1a's at the end of pak file. Trimming...".format(junkbytes))
        while index < endflag + 1:
            segment_length = pak_bytes[index] + pak_bytes[index + 1] * 256
            segment_id = pak_bytes[index + 5]

#            print("* Segment length is {}".format(segment_length))
#            print("* Segment ID is {}".format(segment_id))
            index += 2
            segment_end = index + segment_length
#            print("* Index = {}.  Segment_end = {}.".format(index, segment_end))
            logging.info("Segment ID: {} Index: {} Segment end: {} Length: {}[{}]".format(
                            segment_id,index,segment_end,segment_length,hex(segment_length)))
            segment_bytes = pak_bytes[index:segment_end]
##            print("* Segment bytes: {}".format(segment_bytes.hex(' ')))

            self.segments[segment_id] = segment_bytes
            index += segment_length

    def ingest_from_file(self, pakfile):
        f = open(pakfile, "rb")
        contents = bytes(f.read())
#        print(" * Ingesting Segments from {}:".format(pakfile) + contents.hex(' '))
        logging.info("* Reading segments from : {}   {} bytes".format(pakfile,len(contents)))
        self.parse_pak(contents)

    def get_cloud_pak(self, location, paknum):
        DESKEY=bytes((0x6e, 0x58, 0x61, 0x32, 0x62, 0x79, 0x75, 0x7a))
        DESIV=bytes((0x0c, 0x15, 0x2b, 0x11, 0x39, 0x23, 0x43, 0x1b))
        segnum = "{0:06X}".format(paknum)
        hashstr = hashlib.md5((segnum + "nabu").encode('utf-8')).hexdigest().upper()
        hashstr = "-".join([hashstr[i:i+2] for i in range(0, len(hashstr), 2)])
        npakname = hashstr + ".npak"
        #print(npakname)
        cloudpak = requests.get(location + npakname, headers={"User-Agent": "NABU"})
        if cloudpak.status_code == 404:
            logging.error("#### 404 ERROR! #### - Sending out the penguins.")
            cloudpak = requests.get("{}64-A0-E6-52-56-04-39-8A-D9-3A-3E-77-EF-7E-25-BE.npak".format(location), headers={"User-Agent": "NABU"})
        encryptedpak = cloudpak.content
        cipher = DES.new(DESKEY, DES.MODE_CBC, iv=DESIV)
        pakdata = cipher.decrypt(encryptedpak)
        pakdata = Padding.unpad(pakdata, 8)
        self.parse_pak(pakdata)


class NabuSegment:
    def __init__(self):
        pak_pak_id = None
        pak_segmentnum = None
        pak_owner = None
        pak_tier = None
        pak_mystery_bytes = None
        segment_type = None
        segment_number = None
        segment_offset = None
        segment_crc = None
        segment_bytes = None

    def ingest_bytes(self, segment_bytes):
        self.pak_id = bytes(segment_bytes[0:3])
        self.segmentnum = bytes(segment_bytes[3:4])
        self.pak_owner = bytes(segment_bytes[4:5])
        self.pak_tier = bytes(segment_bytes[5:9])
        self.pak_mystery_bytes = bytes(segment_bytes[9:11])
        self.segment_type = bytes(segment_bytes[11:12])
        self.segment_number = bytes(segment_bytes[12:14])
        self.segment_offset = bytes(segment_bytes[14:16])
        self.segment_crc = bytes(segment_bytes[-2:])
        self.segment_bytes = segment_bytes

    def __init__(self):
        self.crctable = [0x0000, 0x1021, 0x2042, 0x3063, 0x4084, 0x50a5, 0x60c6, 0x70e7, 0x8108, 0x9129, 0xa14a, 0xb16b, 0xc18c, 0xd1ad, 0xe1ce, 0xf1ef, 0x1231, 0x0210, 0x3273, 0x2252, 0x52b5, 0x4294, 0x72f7, 0x62d6, 0x9339, 0x8318, 0xb37b, 0xa35a, 0xd3bd, 0xc39c, 0xf3ff, 0xe3de, 0x2462, 0x3443, 0x0420, 0x1401, 0x64e6, 0x74c7, 0x44a4, 0x5485, 0xa56a, 0xb54b, 0x8528, 0x9509, 0xe5ee, 0xf5cf, 0xc5ac, 0xd58d, 0x3653, 0x2672, 0x1611, 0x0630, 0x76d7, 0x66f6, 0x5695, 0x46b4, 0xb75b, 0xa77a, 0x9719, 0x8738, 0xf7df, 0xe7fe, 0xd79d, 0xc7bc, 0x48c4, 0x58e5, 0x6886, 0x78a7, 0x0840, 0x1861, 0x2802, 0x3823, 0xc9cc, 0xd9ed, 0xe98e, 0xf9af, 0x8948, 0x9969, 0xa90a, 0xb92b, 0x5af5, 0x4ad4, 0x7ab7, 0x6a96, 0x1a71, 0x0a50, 0x3a33, 0x2a12, 0xdbfd, 0xcbdc, 0xfbbf, 0xeb9e, 0x9b79, 0x8b58, 0xbb3b, 0xab1a, 0x6ca6, 0x7c87, 0x4ce4, 0x5cc5, 0x2c22, 0x3c03, 0x0c60, 0x1c41, 0xedae, 0xfd8f, 0xcdec, 0xddcd, 0xad2a, 0xbd0b, 0x8d68, 0x9d49, 0x7e97, 0x6eb6, 0x5ed5, 0x4ef4, 0x3e13, 0x2e32, 0x1e51, 0x0e70, 0xff9f, 0xefbe, 0xdfdd, 0xcffc, 0xbf1b, 0xaf3a, 0x9f59,
                         0x8f78, 0x9188, 0x81a9, 0xb1ca, 0xa1eb, 0xd10c, 0xc12d, 0xf14e, 0xe16f, 0x1080, 0x00a1, 0x30c2, 0x20e3, 0x5004, 0x4025, 0x7046, 0x6067, 0x83b9, 0x9398, 0xa3fb, 0xb3da, 0xc33d, 0xd31c, 0xe37f, 0xf35e, 0x02b1, 0x1290, 0x22f3, 0x32d2, 0x4235, 0x5214, 0x6277, 0x7256, 0xb5ea, 0xa5cb, 0x95a8, 0x8589, 0xf56e, 0xe54f, 0xd52c, 0xc50d, 0x34e2, 0x24c3, 0x14a0, 0x0481, 0x7466, 0x6447, 0x5424, 0x4405, 0xa7db, 0xb7fa, 0x8799, 0x97b8, 0xe75f, 0xf77e, 0xc71d, 0xd73c, 0x26d3, 0x36f2, 0x0691, 0x16b0, 0x6657, 0x7676, 0x4615, 0x5634, 0xd94c, 0xc96d, 0xf90e, 0xe92f, 0x99c8, 0x89e9, 0xb98a, 0xa9ab, 0x5844, 0x4865, 0x7806, 0x6827, 0x18c0, 0x08e1, 0x3882, 0x28a3, 0xcb7d, 0xdb5c, 0xeb3f, 0xfb1e, 0x8bf9, 0x9bd8, 0xabbb, 0xbb9a, 0x4a75, 0x5a54, 0x6a37, 0x7a16, 0x0af1, 0x1ad0, 0x2ab3, 0x3a92, 0xfd2e, 0xed0f, 0xdd6c, 0xcd4d, 0xbdaa, 0xad8b, 0x9de8, 0x8dc9, 0x7c26, 0x6c07, 0x5c64, 0x4c45, 0x3ca2, 0x2c83, 0x1ce0, 0x0cc1, 0xef1f, 0xff3e, 0xcf5d, 0xdf7c, 0xaf9b, 0xbfba, 0x8fd9, 0x9ff8, 0x6e17, 0x7e36, 0x4e55, 0x5e74, 0x2e93, 0x3eb2, 0x0ed1, 0x1ef0]

    def get_time_segment(self):
        now = datetime.datetime.now()
        time_bytes = bytearray([])
        time_bytes[0:3] = [127, 255, 255]  # segment ID = 0x7fffff
        time_bytes[3:4] = [0]  # packet number = 0x00
        time_bytes[4:5] = [1]  # owner = 0x01
        time_bytes[5:9] = [127, 255, 255, 255]  # tier = 0x7fffffff
        time_bytes[9:11] = [127, 128]  # mystery byte = 0x7f80
        time_bytes[11:12] = [32]  # pack type = 0x20 (16 for 0x10)
        time_bytes[12:14] = [0, 0]  # packet number zero
        time_bytes[14:16] = [0, 0]  # offset zero
        time_bytes[16:18] = [2, 2]  # , 84, 1, 1, 0, 40, 0]
        time_bytes[18:19] = [(now.weekday()+2) % 7]
        time_bytes[19:20] = [83]  # 1983
        time_bytes[20:21] = [now.month]
        time_bytes[21:22] = [now.day]
        time_bytes[22:23] = [now.hour]
        time_bytes[23:24] = [now.minute]
        time_bytes[24:25] = [now.second]
#        self.timeseg = time_bytes[0:25]
        timeseg = self.add_checksum(time_bytes[0:25])
        return timeseg

    def add_checksum(self, segment_data):
        seglength = len(segment_data)
        crc = 65535
        for z in segment_data:
            #            print("byte", z)
            checksum = (crc >> 8 ^ z)
            checksum = hex(checksum & 0xff)
            checksum = int(checksum, 0)
            crc <<= 8
            crc = int(hex(crc & 0xffff), 0)
            crc ^= self.crctable[checksum]
            crc = int(hex(crc & 0xffff), 0)
        crcbyte1 = (int(int(hex(crc & 0xff00), 0)/256)) ^ 0xff
#        print("crcbyte1", crcbyte1, hex(crcbyte1))
        crcbyte2 = (int(hex(crc & 0x00ff), 0)) ^ 0xff
#        print("crcbyte2", crcbyte2, hex(crcbyte2))
        segment_data[seglength:seglength+2] = bytes([crcbyte1, crcbyte2])
        return segment_data
