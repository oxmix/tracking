#!/usr/bin/env python3
# author: Oxmix
# coding: utf-8

from tracking import Tracking

Tracking({
    'host': '0.0.0.0',
    'port': 3456,
    'client_max': 5,
    'client_timeout': 80,
    'redis_host': '127.0.0.1',
    'redis_port': 6379,
    'redis_db': 0,
    'redis_channel': 'tracking',
    'debug': False
}).run()
