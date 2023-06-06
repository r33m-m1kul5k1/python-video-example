import json
import select
import socket
from argparse import ArgumentParser
from queue import Queue, Full, Empty
from threading import Thread

from cv2 import VideoCapture, putText, imshow, waitKey, FONT_HERSHEY_COMPLEX_SMALL


class CaptureThread(Thread):
    def __init__(self, uri: str, queue: Queue):
        super(CaptureThread, self).__init__()
        self.uri = uri
        self.queue = queue
        self.closed = False
        self.finished = False

    def run(self):
        print("starting video capture thread...")
        cap = VideoCapture(self.uri)
        try:
            while cap.isOpened() and not self.closed:
                ret, frame = cap.read()
                if ret:
                    try:
                        self.queue.put_nowait(frame)
                    except Full:
                        self.queue.get_nowait()
                        self.queue.put_nowait(frame)
        finally:
            self.finished = True
            cap.release()

    def isFinished(self):
        return self.finished

    def close(self):
        self.closed = True


class TelemetryThread(Thread):
    def __init__(self, port: int, bufsize: int):
        super(TelemetryThread, self).__init__()
        self.port = port
        self.bufsize = bufsize
        self.closed = False
        self.finished = False
        self.latest_telemetry = None

    def run(self):
        print("starting api thread...")
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.connect(('127.0.0.1', self.port))
            s.setblocking(False)
            while not self.closed:
                ready = select.select([s], [], [], 1)
                if ready[0]:
                    data, addr = s.recvfrom(self.bufsize)
                    temp = json.loads(data.decode('UTF-8'))
                    if temp["messageType"] == "telemetry":
                        self.latest_telemetry = temp
        finally:
            self.finished = True
            s.close()

    def isFinished(self):
        return self.finished

    def getLatestAsDict(self):
        return self.latest_telemetry.copy()

    def close(self):
        self.closed = True


def print_from_telemetry(telemetry_to_print, key_name: str, accuracy=None):
    temp = telemetry_to_print[key_name]
    if temp is None:
        return "N/A"
    if accuracy is None:
        return temp
    return f'{temp:.{accuracy}f}'


if __name__ == '__main__':
    parser = ArgumentParser('python3 example.py')
    parser.add_argument('--video-port', type=int, default=47000, help='The TCP port to listen on for encoded video.')
    parser.add_argument('--telemetry-port', type=int, default=48000, help='The TCP port to listen on for telemetry.')
    parser.add_argument('--telemetry-bufsize', type=int, default=10240,
                        help='The buffer size for a single telemetry message.')
    ns = parser.parse_args()

    # If you've buily opencv with cuvid support, or support for another hardware decoder, specify it here:
    # os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = "video_codec;h264_cuvid"

    closing = False
    while not closing:
        capture_queue = Queue(2)
        capture_thread = CaptureThread('tcp://127.0.0.1:{}?listen'.format(ns.video_port), capture_queue)
        telemetry_thread = TelemetryThread(ns.telemetry_port, ns.telemetry_bufsize)

        try:
            capture_thread.start()
            telemetry_thread.start()
            timeout = None
            while not closing and not capture_thread.isFinished() and not telemetry_thread.isFinished():
                img = capture_queue.get(timeout=timeout)
                telemetry = telemetry_thread.getLatestAsDict()
                putText(img, f'Press ESC to quit. '
                             f'Camera model: {print_from_telemetry(telemetry, "cameraModel")}'
                             f'({print_from_telemetry(telemetry, "displayType")}), '
                             f'Altitude: {print_from_telemetry(telemetry, "aboveHomeAltitude", 1)}, '
                             f'Lat: {print_from_telemetry(telemetry, "lat", 6)}, '
                             f'Lon: {print_from_telemetry(telemetry, "lon", 6)}',
                        (30, 30), FONT_HERSHEY_COMPLEX_SMALL, 0.8, (200, 200, 250))
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
