import threading

import pygame_sdl2 as pygame
from util import set_thread_name
import events
import keys


class Screen():
    def __init__(self):
        self.frames = 120
        size = width, height = 1024, 700
        self.screen = pygame.display.set_mode(size)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font('basis33.ttf', 16)
        text = self.font.render('M', False, (255,255,255), (0,0,0))
        self.ux, self.uy = text.get_size()
        self._font_render_cache = {}

    def timeout(self, time):
        self.frames = time

    def addstr(self, y, x, text, attr=None):
        color = (255, 255, 31) if bool(attr) else (255,255,255)
        text_key = (text, color)

        text_render = self._font_render_cache.get(text_key, None)
        if not text_render:
            text_render = self.font.render(text, False, color, (0,0,0))
            self._font_render_cache[text_key] = text_render

        x1, y1 = self.ux*x, self.uy*y
        w, h = text_render.get_size()
        self.screen.fill(pygame.Color("black"), (x1, y1, w, h))
        self.screen.blit(text_render, (x1 ,y1))

    def refresh(self, *args):
        pygame.display.flip()
        self.clock.tick(self.frames)

    def erase(self):
        self.screen.fill(pygame.Color("black"))

    def textbox(self, y, x, width, value="", edit=False):
        #Draw a textbox and return the exit key
        value = str(value)
        cursor = '_' if edit else ''

        attr = keys.A_BOLD if edit else None
        self.addstr(y, x, '[{value: <{width}}]'.format(value=value+cursor, width=width), attr)
        self.refresh()
        k = None
        while edit:
            try:
                ev = events.get()
            except:
                continue

            if ev.event_type not in [events.EVENT_KEY_DOWN, events.EVENT_KEY_UP]:
                return 0, ev

            if ev.event_type == events.EVENT_KEY_UP:
                continue

            k = ev.key_code
            if k in [keys.KEY_ENTER, keys.KEY_UP, keys.KEY_DOWN, keys.KEY_TAB, keys.KEY_STAB, keys.KEY_ESC]:
                edit = False
            elif k in [keys.KEY_LEFT, keys.KEY_RIGHT]:
                if value.isdigit():
                    diff = -1 if k == keys.KEY_LEFT else 1
                    value = int(value)
                    value += diff
                    value = str(value)
                    edit = False
            elif k == keys.KEY_BACKSPACE:
                value = value[:-1]
            elif ev.char and len(value) < width:
                value += ev.char
        
            self.addstr(y, x, '[{value: <{width}}]'.format(value=value+'_', width=width), attr)
            self.refresh()

        return k, value

    def listbox(self, y, x, width, value="", options=None, edit=False):
        #Draw a textbox and return the exit key
        value = str(value)
        options = ['Undefined'] if options is None else options

        attr = keys.A_BOLD if edit else None
        self.addstr(y, x, '[< {value: <{width}} >]'.format(value=value, width=width-4), attr)
        self.refresh()
        k = None
        while edit:
            try:
                ev = events.get()
            except:
                continue

            if ev.event_type != events.EVENT_KEY_DOWN:
                continue

            k = ev.key_code
            if k in [keys.KEY_ENTER, keys.KEY_UP, keys.KEY_DOWN, keys.KEY_TAB, keys.KEY_STAB, keys.KEY_ESC]:
                edit = False
            elif k in [keys.KEY_LEFT, keys.KEY_RIGHT]:
                if value in options:
                    pos = options.index(value)
                    change = -1 if k == keys.KEY_LEFT else 1
                    pos = (pos+change) % len(options)
                else:
                    pos = 0
                value = options[pos]
                edit = False
        
            self.addstr(y, x, '[< {value: <{width}} >]'.format(value=value, width=width-4), attr)
            self.refresh()

        return k, value

def noecho():
    pass

def cbreak():
    pass

def initscr():
    pygame.init()
    return Screen()


class PyGameThread(threading.Thread):
    def __init__(self):
        super(PyGameThread, self).__init__()
        set_thread_name("beatkit kbrd")
        self._run = threading.Event()
        self._run.set()

    def run(self):
        shift = False
        ctrl = False
        alt = False
        clock = pygame.time.Clock()
        while self._run.is_set():
            for event in pygame.event.get():
                if event.type not in [pygame.KEYDOWN, pygame.KEYUP]:
                    continue
                if event.key in [pygame.K_RSHIFT, pygame.K_LSHIFT]:
                    shift = (event.type == pygame.KEYDOWN)
                elif event.key in [pygame.K_RCTRL, pygame.K_LCTRL]:
                    ctrl = (event.type == pygame.KEYDOWN)
                elif event.key in [pygame.K_RALT, pygame.K_LALT]:
                    alt = (event.type == pygame.KEYDOWN)
                elif event.type == pygame.KEYDOWN:
                    if shift:
                        if event.key == pygame.K_DOWN:
                            event.key = keys.KEY_SF
                        elif event.key == pygame.K_UP:
                            event.key = keys.KEY_SR
                        elif event.key == pygame.K_LEFT:
                            event.key = keys.KEY_SLEFT
                        elif event.key == pygame.K_RIGHT:
                            event.key = keys.KEY_SRIGHT
                        elif event.key == pygame.K_TAB:
                            event.key = keys.KEY_STAB

                    events.put(events.KeyboardDownEvent(event.key, event.unicode))
                elif event.type == pygame.KEYUP:
                    events.put(events.KeyboardUpEvent(event.key, chr(event.key & 0xff)))
            clock.tick(120)
        
    def stop(self):
        self._run.clear()

class Menu(object):
    def __init__(self, scr, commands = []):
        self.commands = commands
        self.scr = scr

    def run(self):
        curr_command = ''
        self.print_commands(curr_command)
        while True:
            try:
                ev = events.get()
            except:
                continue

            if ev.event_type != events.EVENT_KEY_DOWN:
                continue

            k = ev.key_code
            c = chr(k & 0xff)
            if k == keys.KEY_ESC:
                curr_command = ''
                break
            if k == keys.KEY_ENTER:
                break
            elif k == keys.KEY_BACKSPACE:
                curr_command = curr_command[:-1]
            elif ev.char:
                curr_command += ev.char
            self.print_commands(curr_command)

        cmd = curr_command.split(' ',1)
        if len(cmd) == 1:
            return cmd[0], None
        return cmd[0], cmd[1]

    def print_commands(self, command_line):
        self.scr.erase()
        cmd_list = command_line.split(' ', 1)
        curr_command = cmd_list[0]
        y = 0
        for command in self.commands:
            if command[0] == curr_command or (len(cmd_list) == 1 and command[0].startswith(curr_command)):
                self.mprint(y, 0, ' '.join(command[1]))
                y += 1
        if not y:
            self.scr.addstr(0, 0, 'Invalid command')
            y += 1

        self.scr.addstr(y, 0, ':{}'.format(command_line))
        self.scr.refresh(0,0, 0,0, 30,100)

    def mprint(self, y, x, menu):
        attr = 0
        for i, c in enumerate(menu):
            if c == '_':
                attr = keys.A_BOLD
            else:
                self.scr.addstr(y, x+i, c, attr)
                attr = 0




if __name__ == "__main__":
    scr = initscr()
    keychars = PyGameThread()
    keychars.start()
    scr.addstr(1,1,'Hello')
    scr.addstr(2,1,'Hello')
    scr.addstr(3,2,'Hello')
    scr.refresh()
    while True:
        try:
            ev = events.get()
        except:
            continue

        if ev.event_type == events.EVENT_KEY_DOWN:
            if ev.key_code == pygame.K_q:
                break
        scr.addstr(1,1,'Hello')
        scr.addstr(2,1,'Hello')
        scr.addstr(3,2,'Hello')
        scr.refresh()
    scr.textbox(4,1,30, 'Test Value', edit=True)
    scr.listbox(4,1,30, 'Test Value', options=['aa', 'bb', 'cc'],edit=True)

    command, parameters = Menu(scr, commands = [
        ('n', ['_New']),
        ('o', ['_Open']),
        ('s', ['_Save']),
        ('np', ['_New', '_Pattern']),
        ('dp', ['_Duplicate', '_Pattern']),
        ('ep', ['_Edit', '_Pattern']),
        ('epn', ['_Edit', '_Pattern', '_Name']),
        ('rp', ['_Remove', '_Pattern']),
        ('bpm', ['_Beats _per _minute']),
        ('q', ['_Quit']),
    ]).run()

    keychars.stop()
