import socket,urllib.request,urllib.error
def blocked(*args,**kwargs): raise urllib.error.URLError('synthetic offline contract')
socket.socket.connect=blocked;socket.create_connection=blocked;socket.getaddrinfo=blocked
urllib.request.urlopen=blocked
