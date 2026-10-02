import requests
from requests import Request


def pause_print():
    r = Request('POST', 'http://localhost:7125/printer/print/pause')
    print("Printer said: " + r.text)