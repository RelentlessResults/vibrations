import Queue
import math
import multiprocessing
import threading
import sys
from random import random, randrange

import numpy as np
import pyaudio
import time
from getch import getch, pause

from _Getch import _Getch

rate = 44100
active_sound_data = []
current_read_index = 0

def sine(frequency, length, fade_duraion):
    fade_samples = int(fade_duraion * rate)
    length = int(length * rate)
    factor = float(frequency) * (math.pi * 2) / rate
    fade_in = np.arange(0.0, 1.0, 1.0/float(fade_samples))
    fade_in = np.pad(fade_in, (0, length-len(fade_in)), 'constant', constant_values=(0, 1))
    fade_out = np.arange(1.0, 0.0, -1.0/float(fade_samples))
    fade_out = np.pad(fade_out, (length-len(fade_out), 0), 'constant', constant_values=(1, 0))
    result = np.sin(np.arange(length) * factor)
    result = result * fade_in * fade_out
    return result


def get_tone(frequency, amplitude_left, amplitude_right, length=3):
    padding_length = rate * 0.3
    noise = np.concatenate([np.zeros(padding_length), sine(frequency, length, 0.05), np.zeros(padding_length)])
    chunk = np.empty(2 * noise.size, dtype=noise.dtype)
    chunk[0::2] = noise * amplitude_left
    chunk[1::2] = noise * amplitude_right
    return chunk

def continue_stream(in_data, frames_per_buffer, time_info, status):
    global active_sound_data
    global current_read_index
    data_start = current_read_index
    data_end = current_read_index + (2 * frames_per_buffer)
    data_length = data_end - data_start
    result = active_sound_data[data_start:data_end]
    if result.size < data_length:
        result = np.append(result, np.zeros(data_length - result.size))
        print 'adding buffer padding'
    current_read_index += data_length
    flag = pyaudio.paComplete if current_read_index > active_sound_data.size else pyaudio.paContinue
    return (result.astype(np.float32).tostring(), flag)

# def heardKey():
#     i,o,e = select.select([sys.stdin], [], [], 0)
#     for s in i:
#         if s == sys.stdin:
#             input = sys.stdin.readline()
#             return True
#     return False


class _GetchUnix:
    def __init__(self):
        import tty, sys
        from select import select

    def __call__(self):

        import sys, tty, termios
        from select import select
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(sys.stdin.fileno())
            [i, o, e] = select([sys.stdin.fileno()], [], [], 0.2)
            if i:
                ch = sys.stdin.read(1)
            else:
                ch = ''
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

def add_input(input_queue, termination_queue):
    getch = _GetchUnix()
    while termination_queue.empty():
        input_queue.put(getch())



def test_user(frequency, amplitude, channel):
    global active_sound_data, current_read_index
    print 'Testing ' + str(frequency) + 'Hz, Amplitude ' + str(amplitude) + ', Channel: ' + str(channel)
    p = pyaudio.PyAudio()
    amp_l = amplitude if channel == 0 else 0
    amp_r = amplitude - amp_l
    active_sound_data = get_tone(frequency, amp_l, amp_r)
    current_read_index = 0
    stream = p.open(format=pyaudio.paFloat32, channels=2, rate=rate, output=1, stream_callback=continue_stream)
    stream.start_stream()

    input_queue = Queue.Queue()
    termination_queue = Queue.Queue()
    input_thread = threading.Thread(target=add_input, args=(input_queue,termination_queue))
    input_thread.daemon = True
    input_thread.start()
    result = False
    print 'Q for left, P for right'
    while 1:
        if not stream.is_active():
            print 'sound finished'
            break
        if not input_queue.empty():
            input = input_queue.get().strip()
            print 'input "', input, '"'
            if channel == 0 and 'q' in input:
                result = True
                break
            if channel == 1 and 'p' in input:
                result = True
                break
    termination_queue.put(True)
    stream.stop_stream()
    stream.close()
    p.terminate()
    time.sleep(2)
    print 'PASS' if result else 'FAIL'
    return result

class QuerySet:
    def __init__(self, frequency, channel):
        self.top = 1
        self.bottom = 0
        self.frequency = frequency
        self.channel = channel

    def get_test_amplitude(self):
        return self.bottom + 0.5 * (self.top - self.bottom)

    def is_complete(self):
        return (self.top - self.bottom) < 0.1

    def result_amplitude(self):
        return (self.top - self.bottom) * 0.5 + self.bottom

    def register_result(self, amplitude, can_hear):
        if can_hear:
            self.top = amplitude
        else:
            self.bottom = amplitude

    def get_report(self):
        return ("L" if self.channel == 0 else "R") + ", " + str(self.frequency) + "Hz, " + str(self.result_amplitude()) +\
               " ( min: "+str(self.bottom) + " max: " + str(self.top)+" )"

if __name__ == '__main__':
    frequencies = [50, 130, 260, 500, 1000, 2000, 4000, 8000]
    query_set = map(lambda f: QuerySet(f, 0), frequencies) + map(lambda f: QuerySet(f, 1), frequencies)
    while True:
        unfinished_queries = filter(lambda q: not q.is_complete(), query_set)
        if len(unfinished_queries) < 1:
            break
        idx = int(random() * len(unfinished_queries))
        q = unfinished_queries[idx]
        amp = q.get_test_amplitude()
        result = test_user(q.frequency, amp, q.channel)
        q.register_result(amp, result)

    print "Report below:"
    for q in query_set:
        print q.get_report()