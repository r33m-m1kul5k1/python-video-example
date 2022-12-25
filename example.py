from cv2 import VideoCapture, putText, imshow, waitKey, FONT_HERSHEY_COMPLEX_SMALL
from threading import Thread
from queue import Queue, Full, Empty
from argparse import ArgumentParser
import socket, select, json

class CaptureThread(Thread):
  def __init__(self, uri: str, queue: Queue):
    super(CaptureThread, self).__init__()
    self.uri = uri
    self.queue = queue
    self.closed = False
    self.finished = False
  def run(self):
    cap = VideoCapture(self.uri)
    while cap.isOpened() and not self.closed:
      ret, frame = cap.read()
      if ret:
        try:
          self.queue.put_nowait(frame)
        except Full:
          self.queue.get_nowait()
          self.queue.put_nowait(frame)
    finished = True
    print('capture thread exited')
  def isFinished(self):
    return self.finished
  def close(self):
    self.closed = True

class TelemetryThread(Thread):
  def __init__(self, port: int, bufsize: int):
    super(TelemetryThread, self).__init__();
    self.port = port
    self.bufsize = bufsize
    self.closed = False
    self.finished = False
    self.latest = None
  def run(self):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.setblocking(0)
    s.bind(('127.0.0.1', self.port))
    while not self.closed:
      ready = select.select([s], [], [], 1)
      if ready[0]:
        data, addr = s.recvfrom(self.bufsize)
        self.latest = data
    self.finished = True
    print("telemetry thread exited")
  def isFinished(self):
    return self.finished
  def getLatestAsDict(self):
    return json.loads(self.latest.decode('UTF-8'))
  def close(self):
    self.closed = True


if __name__ == '__main__':
  parser = ArgumentParser('python3 example.py')
  parser.add_argument('--video-port', type=int, default=47000, help='The TCP port to listen on for encoded video.')
  parser.add_argument('--telemetry-port', type=int, default=9707, help='The UDP port to listen on for telemetry.')
  parser.add_argument('--telemetry-bufsize', type=int, default=10240, help='The buffer size for a single telemetry message.')
  ns = parser.parse_args()
  
  closing = False
  while not closing:
    capture_queue = Queue(2)
    capture_thread = CaptureThread('tcp://127.0.0.1:{}?listen'.format(ns.video_port), capture_queue)
    telemetry_thread = TelemetryThread(ns.telemetry_port, ns.telemetry_bufsize)

    try:
      capture_thread.start()
      telemetry_thread.start()
      timeout = None
      print("Ready")
      while not closing and not capture_thread.isFinished() and not telemetry_thread.isFinished():
        img = capture_queue.get(timeout=timeout)
        telemetry = telemetry_thread.getLatestAsDict()
        putText(img, 'Press ESC to quit. Altitude: {}, LatLon: {}, {}'.format(
          telemetry['airVehicleLocation']['altitude'],
          telemetry['airVehicleLocation']['location']['geometry']['coordinates'][0],
          telemetry['airVehicleLocation']['location']['geometry']['coordinates'][1]
        ), (30, 30), FONT_HERSHEY_COMPLEX_SMALL, 0.8, (200, 200, 250))
        imshow("EyesAtop example", img)
        if waitKey(1) == 27:
          closing = True
        timeout = 2
    except Empty:
      ...
    except KeyboardInterrupt:
      closing = True
    except Exception as ex:
      print(Exception, ex)
    finally:
      print("Session closed, clearing resources...")
      capture_thread.close()
      telemetry_thread.close()
      telemetry_thread.join()
      capture_thread.join()
  