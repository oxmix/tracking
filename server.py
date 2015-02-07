#encoding: utf8
import socket
import sys
import thread
import datetime
import MySQLdb
import setproctitle
import json
import uuid

conf = {
	'server': {
		'host': '1.2.3.4',
		'port': 3333,
		'clientMax': 5,
		'clientTimeout': 60,
		'name': 'beatTracking'
	},
	'db': {
		'host': 'localhost',
		'user': 'user',
		'pass': 'pass',
		'name': 'name',
		'char': 'utf8'
	},
	'debug': {
		'console': False,
		'pack': False
	}
}

def memoryUsageResource():
	import resource
	rusage_denom = 1024.
	if sys.platform == 'darwin':
		# ... it seems that in OSX the output is different units ...
		rusage_denom = rusage_denom * rusage_denom
	mem = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / rusage_denom
	return mem

def crc(dec):
	r = 0x3B
	for d in dec[:-1]:
		r += 0x56 ^ d
		r += 1
		r ^= 0xC5 + d
		r -= 1
	return int(hex(r)[-2:], 16)==dec[-1] and True or False

def convertWork(dec):
	## status
	statusBin = bin(dec[10])[2:].zfill(8)
	power = statusBin[-1]=='0' and 'no' or 'yes' # 0 - bit
	motion = statusBin[-4]=='0' and 'no' or 'yes' # 3 - bit
	packForFixCoord = statusBin[-7]=='1' and 'yes' or 'no' # 6 - bit
	realGPSData = statusBin[-8]=='0' and 'yes' or 'no' # 7 - bit

	## battery Volt
	battery = dec[13]*0.05

	## temperature C.
	oCtemp = dec[44]

	## GSM -dB
	GSMdB = dec[45]

	## GPS status
	gpsStatus = int(bin(dec[54])[2:][0:2], 2) # 6-7 - bit
	gpsValid = (gpsStatus==2 and 'yes' or 'no')
	gpsSputnikQuan, gpsTime, gpsLat, gpsLong = 0, 0, 0.0000, 0.0000
	if gpsValid=='yes' and dec[57]!=0 and dec[56]!=0 and dec[55]!=0:
		gpsSputnikQuan = int(bin(dec[54])[2:][2:8], 2) # 0-5 - bit

		gpsTime = datetime.datetime(
			dec[57]+2000, # год
			dec[56], # месяц
			dec[55], # день
			dec[58], # час
			dec[59], # мин.
			dec[60]  # сек.
		).strftime('%s')

		gpsLat = int( hex(dec[61])[2:].zfill(2) + hex(dec[62])[2:].zfill(2) + hex(dec[63])[2:].zfill(2) + hex(dec[64])[2:].zfill(2) , 16)
		gpsLatMinus = (bin(gpsLat)[2:][0]=='0' and '-' or '') # bits[0] - bit is set => north
		gpsLat = gpsLatMinus+str(gpsLat)[0:2]+'.'+str(float( str(gpsLat)[2:4]+'.'+str(gpsLat)[4:] )/60)[2:6] # convert DD MM.MMMM => DD (MM.MMMM)/60 => DD.DDDD

		gpsLong = int( hex(dec[65])[2:].zfill(2) + hex(dec[66])[2:].zfill(2) + hex(dec[67])[2:].zfill(2) + hex(dec[68])[2:].zfill(2) , 16)
		gpsLongMinus = (bin(gpsLong)[2:][0]=='0' and '-' or '') # bits[0] - bit is set => east
		gpsLong = gpsLongMinus+str(gpsLong)[0:2]+'.'+str(float( str(gpsLong)[2:4]+'.'+str(gpsLong)[4:] )/60)[2:6] # convert DD MM.MMMM => DD (MM.MMMM)/60 => DD.DDDD
	else:
		gpsValid = 'no'

	## GPS altitude meter
	gpsAltMeter = dec[69]+dec[70]

	## GPS speed km/h
	gpsSpeedKm = dec[71]*1.852 # 1 uzel = 1.852 km

	## GPS rate degrees
	gpsRateDegrees = dec[72]*2

	## GPS HDOP - Снижение точности в горизонтальной плоскости.
	gpsHDOP = float(dec[73]+dec[74])/10

	# print '---------'
	# print 'gpsValid: '+gpsValid
	# print "power: "+power
	# print "motion: "+motion
	# print "packForFixCoord: "+packForFixCoord
	# print "realGPSData: "+realGPSData
	# print '---------'

	return [(battery, GSMdB, oCtemp, power, motion,
			gpsValid, gpsSputnikQuan, gpsTime, gpsLat, gpsLong, gpsAltMeter, gpsSpeedKm, gpsRateDegrees, gpsHDOP)]

def convertBlackBox(dec):
	result = []

	packAll = dec[1]
	packValid = int(bin(dec[1])[2:].zfill(8)[4:8], 2) # 0-4 - bits

	#print '+ all in black box packed: '+str(packAll)+' / at this pack valid: '+str(packValid)

	for i in range(packValid):
		if i==0:
			offsetByte = 4 # first block
		else:
			offsetByte += 42 # next block

		# more security
		if offsetByte+2 > len(dec):
			break

		## status
		statusBin = bin(dec[1-offsetByte])[2:].zfill(8)
		power = statusBin[-1]=='0' and 'no' or 'yes' # 0 - bit
		motion = statusBin[-4]=='0' and 'no' or 'yes' # 3 - bit
		packForFixCoord = statusBin[-7]=='1' and 'yes' or 'no' # 6 - bit
		realGPSData = statusBin[-8]=='0' and 'yes' or 'no' # 7 - bit

		## battery Volt
		battery = dec[1+offsetByte]*0.05

		## temperature C.
		oCtemp = dec[8+offsetByte]

		## GSM -dB
		GSMdB = dec[9+offsetByte]

		## GPS status
		gpsStatus = int(bin(dec[18+offsetByte])[2:][0:2], 2) # 6-7 - bit
		gpsValid = (gpsStatus==2 and 'yes' or 'no')
		gpsSputnikQuan, gpsTime, gpsLat, gpsLong = 0, 0, 0.0000, 0.0000
		if gpsValid=='yes' and dec[21+offsetByte]!=0 and dec[20+offsetByte]!=0 and dec[19+offsetByte]!=0:
			gpsSputnikQuan = int(bin(dec[18+offsetByte])[2:][2:8], 2) # 0-5 - bit

			gpsTime = datetime.datetime(
				dec[21+offsetByte]+2000, # год
				dec[20+offsetByte], # месяц
				dec[19+offsetByte], # день
				dec[22+offsetByte], # час
				dec[23+offsetByte], # мин.
				dec[24+offsetByte]  # сек.
			).strftime('%s')

			gpsLat = int( hex(dec[25+offsetByte])[2:].zfill(2) + hex(dec[26+offsetByte])[2:].zfill(2) + hex(dec[27+offsetByte])[2:].zfill(2) + hex(dec[28+offsetByte])[2:] , 16)
			gpsLatMinus = (bin(gpsLat)[2:][0]=='0' and '-' or '') # bits[0] - bit is set => north
			gpsLat = gpsLatMinus+str(gpsLat)[0:2]+'.'+str(float( str(gpsLat)[2:4]+'.'+str(gpsLat)[4:] )/60)[2:6] # convert DD MM.MMMM => DD (MM.MMMM)/60 => DD.DDDD

			gpsLong = int( hex(dec[29+offsetByte])[2:].zfill(2) + hex(dec[30+offsetByte])[2:].zfill(2) + hex(dec[31+offsetByte])[2:].zfill(2) + hex(dec[32+offsetByte])[2:] , 16)
			gpsLongMinus = (bin(gpsLong)[2:][0]=='0' and '-' or '') # bits[0] - bit is set => east
			gpsLong = gpsLongMinus+str(gpsLong)[0:2]+'.'+str(float( str(gpsLong)[2:4]+'.'+str(gpsLong)[4:] )/60)[2:6] # convert DD MM.MMMM => DD (MM.MMMM)/60 => DD.DDDD
		else:
			gpsValid = 'no'


		## GPS altitude meter
		gpsAltMeter = dec[33+offsetByte]+dec[34+offsetByte]

		## GPS speed km/h
		gpsSpeedKm = dec[35+offsetByte]*1.852 # 1 uzel = 1.852 km

		## GPS rate degrees
		gpsRateDegrees = dec[36+offsetByte]*2

		## GPS HDOP - Снижение точности в горизонтальной плоскости.
		gpsHDOP = float(dec[37+offsetByte]+dec[38+offsetByte])/10

		block = (battery, GSMdB, oCtemp, power, motion,
				gpsValid, gpsSputnikQuan, gpsTime, gpsLat, gpsLong, gpsAltMeter, gpsSpeedKm, gpsRateDegrees, gpsHDOP)

		result.append(block)

	return result

#_dec = [17,10,210,37,96,52,69,36,80,0,129,0,0,75,24,10,14,6,9,57,24,10,14,12,0,5,160,70,255,255,255,255,17,11,14,12,0,168,192,71,255,255,255,255,34,68,0,250,0,2,19,138,174,5,83,12,11,14,14,54,50,3,86,164,233,2,60,105,153,0,150,0,160,0,5,255,255,178]
#print convertWork(_dec)
#sys.exit()

connectionsList = {}
def clientThread(connection, threadId):
	global conf, connectionsList

	connect = connectionsList[threadId] = {
		'authId': 0,
		'usesId': 0,
		'quanWork': 0,
		'quanBlackBox': 0,
		'quanBadCrc': 0,
		'quanNoValidSputnik': 0,
		'type': 'none',
		'packs': {}
	}

	while True:
		buf = ''
		try:
			buf = connection.recv(1024)
		except socket.timeout:
			if conf['debug']['console']:
				print '+ break connect of timeout'
			break
		except:
			break

		if not buf or buf=='\n':
			break

		if buf.strip()[4:15]=='/cmd/status':
			connect['type'] = 'browser'
			connection.send('HTTP/1.0 200 OK\r\n')
			connection.send('Content-Type: application/json\r\n\r\n')
			connection.send(json.dumps({
				'memUsage': str(memoryUsageResource()),
				'quanConnection': len(connectionsList),
				'connectionsList': connectionsList
			}))
			break

		toDec = lambda x:[int(hex(c), 16) for c in map(ord, x)]

		dec = toDec(buf);

		ctime = datetime.datetime.now().strftime('%s')

		if conf['debug']['pack']:
			toHex = lambda x3:[hex(c)[2:].zfill(2) for c in map(ord, x3)]
			connect['packs'][ctime] = {'dec': dec, 'hex': toHex(buf)}

		if not dec:
			if conf['debug']['console']:
				print '+ device: '+str(connect['authId'])+' - empty toDec'
			break

		if not crc(dec):
			connect['quanBadCrc'] += 1
			if conf['debug']['console']:
				print '+ device: '+str(connect['authId'])+' - bad crc in the pack'
			continue

		dbConnect = MySQLdb.connect(host=conf['db']['host'], user=conf['db']['user'], passwd=conf['db']['pass'], db=conf['db']['name'], charset=conf['db']['char'])
		db = dbConnect.cursor()
		
		### auth
		if(dec[0]==0x10):
			connect['type'] = 'device-autofon'

			if conf['debug']['console']:
				print '+ auth action'

			imei = ''.join( str(hex(x)[2:].zfill(2)) for x in dec[3:11] ).strip('0')

			db.execute('SELECT id, usesId FROM tracking_device WHERE imei = %s ', (imei))
			fto = db.fetchone()
			connect['authId'] = fto[0]
			connect['usesId'] = fto[1]
			
			if(connect['authId']<0):
				break

			connection.send('resp_crc='+chr(dec[11])) #.sendall('1234')

			db.execute('UPDATE tracking_device SET atime = %s WHERE id = %s ', (ctime, connect['authId']))

			if conf['debug']['console']:
				print '+ auth id: '+str(connect['authId'])

		elif(connect['authId']>0 and (dec[0]==0x11 or dec[0]==0x12)):
			if dec[0]==0x11:
				result = convertWork(dec)
				connect['quanWork'] += 1

				if conf['debug']['console']:
					print '+ device: '+str(connect['authId'])+' - query work: '+str(connect['quanWork'])

			if dec[0]==0x12:
				result = convertBlackBox(dec)
				connect['quanBlackBox'] += 1
				
				if conf['debug']['console']:
					print '+ device: '+str(connect['authId'])+' - query black box: '+str(connect['quanBlackBox'])

			for r in result:
				db.execute('UPDATE tracking_device '
					'SET utime = %s, battery = %s, GSMdB = %s, oCtemp = %s, power = %s, motion = %s '
					'WHERE id = %s ',
					(ctime, r[0], r[1], r[2], r[3], r[4], connect['authId'])
				)

				if r[5]=='yes':
					db.execute('SELECT id, lat, `long` FROM tracking_data WHERE did = %s ORDER BY id DESC LIMIT 1', (connect['authId']))
					row = db.fetchone();
					if row and ((str(row[1])==str(r[8]) and str(row[2])==str(r[9])) or r[4]=='no'):
						tdid = row[0]
						db.execute('UPDATE tracking_data SET `repeat` = `repeat`+1, blackBox = %s, sputnikQuan = %s, sputnikTime = %s, `lat` = %s, `long` = %s, altMeter = %s, speedKm = %s, rateDegrees = %s, hdop = %s WHERE id = %s',
							((dec[0]==0x11 and 'no' or 'yes'), r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13], tdid))
					else:
						db.execute('INSERT INTO tracking_data '
							'SET did = %s, usesId = %s, ctime = %s, blackBox = %s, sputnikQuan = %s, sputnikTime = %s, `lat` = %s, `long` = %s, altMeter = %s, speedKm = %s, rateDegrees = %s, hdop = %s',
							(connect['authId'], connect['usesId'], ctime, (dec[0]==0x11 and 'no' or 'yes'), r[6], r[7], r[8], r[9], r[10], r[11], r[12], r[13])
					)
				else:
					connect['quanNoValidSputnik'] += 1
					if conf['debug']['console']:
						print '+ device: '+str(connect['authId'])+' - no vaild sputniks'
		else:
			if conf['debug']['console']:
				print '+ device: '+str(connect['authId'])+' - query bad'

		dbConnect.close()

	connection.close()
	del connectionsList[threadId]
	if conf['debug']['console']:
		print '+ connection.close'

serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serverSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

try:
	serverSocket.bind((conf['server']['host'], conf['server']['port']))
except socket.error as msg:
	print 'Bind failed. Error Code : ' + str(msg[0]) + ' Message ' + msg[1]
	sys.exit()

# maximum connections
serverSocket.listen(conf['server']['clientMax'])

setproctitle.setproctitle(conf['server']['name'])

if conf['debug']['console']:
	print '\n+ server on\n'

try:
	while True:
		# create connect
		connection, address = serverSocket.accept()
		# connect set timeout
		connection.settimeout(conf['server']['clientTimeout'])
		# create thread
		thread.start_new_thread(clientThread, (connection, str(uuid.uuid1())))

	serverSocket.close()
except KeyboardInterrupt:
	serverSocket.close()
	if conf['debug']['console']:
		print '\n+ server off\n'

