# author: Oxmix
# coding: utf-8

import sys
import json
import redis
import socket
import threading
import setproctitle
from datetime import datetime


class Tracking:
    conf = {}
    connections = {}
    connection_seq = 0
    storage = None

    def __init__(self, config):
        self.conf = config
        setproctitle.setproctitle('tracking')
        self.storage = redis.Redis(host=config['redis_host'], port=config['redis_port'], db=config['redis_db'],
                                   encoding='utf-8', decode_responses=True)

    def run(self):
        try:
            socket_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            socket_server.bind((self.conf['host'], self.conf['port']))
        except socket.error as msg:
            sys.exit(str(msg))

        socket_server.listen(self.conf['client_max'])

        self.log('Server on')

        try:
            while True:
                connection, address = socket_server.accept()
                connection.settimeout(self.conf['client_timeout'])
                threading.Thread(target=self.thread, args=(connection,)).start()
        except KeyboardInterrupt:
            socket_server.close()
            self.log('Server off')

    def thread(self, conn):
        self.connection_seq += 1

        self.log('New connect: ' + str(self.connection_seq))

        connect = self.connections[self.connection_seq] = {
            'imei': 'without',
            'default': 0,
            'black_box': 0,
            'bad_crc': 0,
            'type': 'none',
            'packs': {}
        }

        while True:
            try:
                buf = conn.recv(1024)
            except socket.timeout:
                self.disconnect(connect['imei'])
                self.log('Connect: ' + str(self.connection_seq) + ' - break connect of timeout')
                break

            if not buf or buf == '\n':
                self.log('Connect: ' + str(self.connection_seq) + ' - buf empty')
                break

            if self.conf['debug']:
                try:
                    if buf.decode().strip()[4:15] == '/cmd/status':
                        connect['type'] = 'browser'
                        conn.send(b'HTTP/1.0 200 OK\r\n')
                        conn.send(b'Content-Type: application/json\r\n\r\n')
                        conn.send(json.dumps({
                            'seq': self.connection_seq,
                            'mem_usage': self.memory_usage(),
                            'self.connections': self.connections
                        }).encode())
                        break
                except UnicodeDecodeError:
                    pass

            dec = [int(hex(x), 16) for x in buf]
            time = datetime.now().strftime('%s')

            if self.conf['debug']:
                connect['packs'][time] = {'dec': dec,
                                          'hex': [hex(x)[2:].zfill(2) for x in buf]}

            if not dec:
                self.log('Connect: ' + str(self.connection_seq) + ' device: ' + str(connect['imei'])
                         + ' - empty to_dec')
                break

            if not self.crc(dec):
                connect['bad_crc'] += 1
                self.log('Connect: ' + str(self.connection_seq) + ' device: ' + str(connect['imei'])
                         + ' - bad crc in the pack')
                continue

            if dec[0] == 0x10:
                connect['type'] = 'device-autofon'

                connect['imei'] = ''.join(str(hex(x)[2:].zfill(2)) for x in dec[3:11]).strip('0')

                self.log('Connect: ' + str(self.connection_seq) + ' device: ' + str(connect['imei'])
                         + ' - auth')

                if len(connect['imei']) <= 0:
                    break

                conn.send(('resp_crc=' + chr(dec[11])).encode())  # .sendall('1234')

                self.storage.publish(self.conf['redis_channel'], json.dumps({'request': 'connected',
                                                                             'imei': connect['imei']}))

            elif len(connect['imei']) > 0 and (dec[0] == 0x11 or dec[0] == 0x12):
                data = []
                if dec[0] == 0x11:
                    connect['default'] += 1
                    data = self.default(dec)
                if dec[0] == 0x12:
                    connect['black_box'] += 1
                    data = self.black_box(dec)

                self.storage.publish(self.conf['redis_channel'], json.dumps({'request': 'received',
                                                                             'imei': connect['imei'],
                                                                             'data': data}))

                self.log('Connect: ' + str(self.connection_seq) + ' device: ' + str(connect['imei'])
                         + ' - data: ' + str(data))
            else:
                self.log('Connect: ' + str(self.connection_seq) + ' device: ' + str(connect['imei'])
                         + ' - query bad')

        conn.close()
        self.disconnect(connect['imei'])
        del self.connections[self.connection_seq]
        self.log('Connect: ' + str(self.connection_seq) + ' - closed')

    def log(self, message, replace_it=False):
        if not self.conf['debug']:
            return
        message = datetime.strftime(datetime.now(), '[%Y-%m-%d %H:%M:%S]') + ' ' + message
        if replace_it:
            sys.stdout.write("\r" + message + "\033[K\n")
            sys.stdout.write("\033[F")
        else:
            print(message)
        sys.stdout.flush()

    def disconnect(self, imei):
        if imei != 'without':
            self.storage.publish(self.conf['redis_channel'], json.dumps({'request': 'disconnected',
                                                                         'imei': imei}))

    @staticmethod
    def memory_usage():
        import resource
        rusage_den = 1024.
        if sys.platform == 'darwin':
            # ... it seems that in OSX the output is different units ...
            rusage_den = rusage_den * rusage_den
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / rusage_den

    @staticmethod
    def crc(dec):
        r = 0x3B
        for d in dec[:-1]:
            r += 0x56 ^ d
            r += 1
            r ^= 0xC5 + d
            r -= 1
        return int(hex(r)[-2:], 16) == dec[-1] and True or False

    def test_pack_default(self):
        _dec = [17, 10, 210, 37, 96, 52, 69, 36, 80, 0, 129, 0, 0, 75, 24, 10, 14, 6, 9, 57, 24, 10,
                14, 12, 0, 5, 160, 70, 255, 255, 255, 255, 17, 11, 14, 12, 0, 168, 192, 71, 255, 255,
                255, 255, 34, 68, 0, 250, 0, 2, 19, 138, 174, 5, 83, 12, 11, 14, 14, 54, 50, 3, 86,
                164, 233, 2, 60, 105, 153, 0, 150, 0, 160, 0, 5, 255, 255, 178]
        print(self.default(_dec))
        sys.exit()

    @staticmethod
    def default(dec):
        # status
        status_bin = bin(dec[10])[2:].zfill(8)
        power = status_bin[-1] == '0' and 'no' or 'yes'  # 0 - bit
        motion = status_bin[-4] == '0' and 'no' or 'yes'  # 3 - bit
        pack_fix_coord = status_bin[-7] == '1' and 'yes' or 'no'  # 6 - bit
        real_gps_data = status_bin[-8] == '0' and 'yes' or 'no'  # 7 - bit

        # battery Volt
        battery = dec[13] * 0.05

        # temperature C.
        temp_co = dec[44]

        # GSM -dB
        gsm_db = dec[45]

        # GPS status
        gps_status = int(bin(dec[54])[2:][0:2], 2)  # 6-7 - bit
        gps_valid = (gps_status == 2 and 'yes' or 'no')
        gps_sputniks, gps_time, gps_lat, gps_long = 0, 0, 0.0000, 0.0000
        if gps_valid == 'yes' and dec[57] != 0 and dec[56] != 0 and dec[55] != 0:
            gps_sputniks = int(bin(dec[54])[2:][2:8], 2)  # 0-5 - bit

            gps_time = datetime(
                dec[57] + 2000,  # year
                dec[56],  # month
                dec[55],  # day
                dec[58],  # hour
                dec[59],  # min.
                dec[60]  # sec.
            ).strftime('%s')

            gps_lat = int(hex(dec[61])[2:].zfill(2) + hex(dec[62])[2:].zfill(2) +
                          hex(dec[63])[2:].zfill(2) + hex(dec[64])[2:].zfill(2), 16)
            # bits[0] - bit is set => north
            gps_lat_minus = (bin(gps_lat)[2:][0] == '0' and '-' or '')
            # convert DD MM.MMMM => DD (MM.MMMM)/60 => DD.DDDD
            gps_lat = (gps_lat_minus + str(gps_lat)[0:2]
                       + '.' + str(float(str(gps_lat)[2:4] + '.' + str(gps_lat)[4:]) / 60)[2:6])

            gps_long = int(
                hex(dec[65])[2:].zfill(2) + hex(dec[66])[2:].zfill(2) +
                hex(dec[67])[2:].zfill(2) + hex(dec[68])[2:].zfill(2), 16)
            # bits[0] - bit is set => east
            gps_long_minus = (bin(gps_long)[2:][0] == '0' and '-' or '')
            # convert DD MM.MMMM => DD (MM.MMMM)/60 => DD.DDDD
            gps_long = (gps_long_minus + str(gps_long)[0:2]
                        + '.' + str(float(str(gps_long)[2:4] + '.' + str(gps_long)[4:]) / 60)[2:6])
        else:
            gps_valid = 'no'

        # GPS altitude meter
        gps_alt_meter = dec[69] + dec[70]

        # GPS speed km/h
        gps_speed_km = dec[71] * 1.852  # 1 knot = 1.852 km

        # GPS rate degrees
        gps_rate_degrees = dec[72] * 2

        # GPS HDOP - Снижение точности в горизонтальной плоскости.
        gps_hdop = float(dec[73] + dec[74]) / 10

        return [{
            'type': 'default',
            'battery': battery,
            'gsm_db': gsm_db,
            'temp_co': temp_co,
            'power': power,
            'motion': motion,
            'gps_valid': gps_valid,
            'gps_sputniks': gps_sputniks,
            'gps_time': gps_time,
            'gps_lat': gps_lat,
            'gps_long': gps_long,
            'gps_alt_meter': gps_alt_meter,
            'gps_speed_km': gps_speed_km,
            'gps_rate_degrees': gps_rate_degrees,
            'gps_hdop': gps_hdop,
            'pack_fix_coord': pack_fix_coord,
            'real_gps_data': real_gps_data
        }]

    @staticmethod
    def black_box(dec):
        data = []

        # pack_all = dec[1]
        # print('+ all in black box packed: '+str(pack_all)+' / at this pack valid: '+str(pack_valid))
        pack_valid = int(bin(dec[1])[2:].zfill(8)[4:8], 2)  # 0-4 - bits

        offset = 0
        for i in range(pack_valid):
            if i == 0:
                offset = 4  # first block
            else:
                offset += 42  # next block

            # more security
            if offset + 2 > len(dec):
                break

            # status
            status_bin = bin(dec[1 - offset])[2:].zfill(8)
            power = status_bin[-1] == '0' and 'no' or 'yes'  # 0 - bit
            motion = status_bin[-4] == '0' and 'no' or 'yes'  # 3 - bit
            pack_fix_coord = status_bin[-7] == '1' and 'yes' or 'no'  # 6 - bit
            real_gps_data = status_bin[-8] == '0' and 'yes' or 'no'  # 7 - bit

            # battery Volt
            battery = dec[1 + offset] * 0.05

            # temperature C.
            temp_co = dec[8 + offset]

            # GSM -dB
            gsm_db = dec[9 + offset]

            # GPS status
            gps_status = int(bin(dec[18 + offset])[2:][0:2], 2)  # 6-7 - bit
            gps_valid = (gps_status == 2 and 'yes' or 'no')
            gps_sputniks, gps_time, gps_lat, gps_long = 0, 0, 0.0000, 0.0000
            if gps_valid == 'yes' and dec[21 + offset] != 0 and dec[20 + offset] != 0 and dec[19 + offset] != 0:
                gps_sputniks = int(bin(dec[18 + offset])[2:][2:8], 2)  # 0-5 - bit

                gps_time = datetime(
                    dec[21 + offset] + 2000,  # year
                    dec[20 + offset],  # month
                    dec[19 + offset],  # day
                    dec[22 + offset],  # hour
                    dec[23 + offset],  # min.
                    dec[24 + offset]  # sec.
                ).strftime('%s')

                gps_lat = int(hex(dec[25 + offset])[2:].zfill(2) + hex(dec[26 + offset])[2:].zfill(2) +
                              hex(dec[27 + offset])[2:].zfill(2) + hex(dec[28 + offset])[2:], 16)
                # bits[0] - bit is set => north
                gps_lat_minus = (bin(gps_lat)[2:][0] == '0' and '-' or '')
                # convert DD MM.MMMM => DD (MM.MMMM)/60 => DD.DDDD
                gps_lat = (gps_lat_minus + str(gps_lat)[0:2]
                           + '.' + str(float(str(gps_lat)[2:4] + '.' + str(gps_lat)[4:]) / 60)[2:6])

                gps_long = int(hex(dec[29 + offset])[2:].zfill(2) +
                               hex(dec[30 + offset])[2:].zfill(2) +
                               hex(dec[31 + offset])[2:].zfill(2) + hex(dec[32 + offset])[2:], 16)
                # bits[0] - bit is set => east
                gps_long_minus = (bin(gps_long)[2:][0] == '0' and '-' or '')
                # convert DD MM.MMMM => DD (MM.MMMM)/60 => DD.DDDD
                gps_long = (gps_long_minus + str(gps_long)[0:2]
                            + '.' + str(float(str(gps_long)[2:4] + '.' + str(gps_long)[4:]) / 60)[2:6])
            else:
                gps_valid = 'no'

            # GPS altitude meter
            gps_alt_meter = dec[33 + offset] + dec[34 + offset]

            # GPS speed km/h
            gps_speed_km = dec[35 + offset] * 1.852  # 1 knot = 1.852 km

            # GPS rate degrees
            gps_rate_degrees = dec[36 + offset] * 2

            # GPS HDOP - Снижение точности в горизонтальной плоскости.
            gps_hdop = float(dec[37 + offset] + dec[38 + offset]) / 10

            data.append({
                'type': 'black-box',
                'battery': battery,
                'gsm_db': gsm_db,
                'temp_co': temp_co,
                'power': power,
                'motion': motion,
                'gps_valid': gps_valid,
                'gps_sputniks': gps_sputniks,
                'gps_time': gps_time,
                'gps_lat': gps_lat,
                'gps_long': gps_long,
                'gps_alt_meter': gps_alt_meter,
                'gps_speed_km': gps_speed_km,
                'gps_rate_degrees': gps_rate_degrees,
                'gps_hdop': gps_hdop,
                'pack_fix_coord': pack_fix_coord,
                'real_gps_data': real_gps_data
            })

        return data
