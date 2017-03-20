# encoding: utf-8

from kivy.config import Config
Config.set('input', 'mouse', 'mouse') # noqa

from math import cos, sin, radians
from object_renderer import DataRenderer
from kivy.core.window import Window  # noqa
from kivy.lang import Builder
from kivy.properties import AliasProperty, DictProperty
from kivy.clock import Clock
from kivy.app import App
from threading import Thread, Lock
from liblas import file as las
from os.path import splitext, exists
from itertools import dropwhile


def dist(p1, p2):
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** .5


def dist3(p1, p2):
    return (
        (p1[0] - p2[0]) ** 2 +
        (p1[1] - p2[1]) ** 2 +
        (p1[2] - p2[2]) ** 2
    ) ** .5


def cross(a, b):
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0]
    )


class View(DataRenderer):
    loaders = DictProperty()

    def __init__(self, **kwargs):
        super(View, self).__init__(**kwargs)
        self.touches = []
        self.touches_center = []
        self.touches_dist = 0
        Clock.schedule_interval(self.update_cam, 0)

    def on_touch_down(self, touch):
        if super(View, self).on_touch_down(touch):
            return True

        if self.collide_point(*touch.pos):
            self.touches.append(touch)
            touch.grab(self)
            if len(self.touches) > 1:
                self.touches_center = self.get_center()
                self.touches_dist = self.get_dist(self.touches_center)

            return True

    def get_direction_vector(self):
        ax = radians(self.cam_rotation[0])
        az = radians(self.cam_rotation[2])

        return [
            - sin(az),
            - cos(az),
            sin(ax + 90)
        ]

    direction_vector = AliasProperty(
        get_direction_vector, bind=['cam_rotation'])

    def update_cam(self, dt):
        if not self.touches:
            return

        elif len(self.touches) == 1:
            self.cam_rotation[2] += self.touches[0].dx / 10.  # pitch
            self.cam_rotation[0] -= self.touches[0].dy / 10.  # yaw

        else:
            c = self.get_center()
            d = self.get_dist(c)

            vec = self.direction_vector
            zoom = min(5, max(-5, (d - self.touches_dist)))

            # get the cross product of direction vector to vertical
            # axis, to get our first translation vector
            v1 = cross(vec, (0, 0, -1))
            # get the cross product of direction vector with first vector
            # to get a second translation vector coplanar and orthogonal
            # to the first translation vector
            v2 = cross(vec, v1)

            strafe = (
                c[0] - self.touches_center[0],
                c[1] - self.touches_center[1]
            )

            strafe_vector = (
                strafe[0] * v1[0] + strafe[1] * v2[0],
                strafe[0] * v1[1] + strafe[1] * v2[1],
                strafe[0] * v1[2] + strafe[1] * v2[2]
            )

            ct = self.cam_translation
            ct[0] += (vec[0] * zoom + strafe_vector[0] / 50.) * 10000
            ct[1] += (vec[1] * zoom + strafe_vector[1] / 50.) * 10000
            ct[2] += (vec[2] * zoom + strafe_vector[2] / 50.) * 10000

            self.touches_center = c
            self.touches_dist = d
        return True

    def get_boxes(self):
        CUT = 100

        min_ = self.min_
        max_ = self.max_
        x, y, z = [int(x) for x in self.cam_translation]

        x_min, y_min = min_[0], min_[1]
        x_max, y_max = max_[0], max_[1]

        x_inc = (x_max - x_max) / CUT
        y_inc = (y_max - y_max) / CUT

        for Xi in xrange(CUT):
            for Yi in xrange(CUT):
                if (Xi, Yi) not in self.indexes:
                    # print "ignoring {},{}".format(Xi, Yi)
                    continue

                X = x_min + Xi * x_inc
                Y = y_min + Yi * y_inc

                yield((Xi, Yi), dist3((X, Y, 0), (x, y, z)))

    def on_cam_translation(self, *args):
        super(View, self).on_cam_translation(*args)
        boxes = self.get_boxes()

        distances = [
            (10 ** 4, 1),
            (10 ** 5, .1),
            (10 ** 6, .01),
            (float('inf'), .001),
        ]

        min_d = max_d = float('inf')
        for box, distance in boxes:
            min_d = min(min_d, distance)
            max_d = min(max_d, distance)
            c = list(dropwhile(lambda x: x[0] < distance, distances))
            density = c[0][1]
            if box in self.indexes:
                self.load_box(box, density)
        print min_d, max_d

        self.cross.vertices = [
            -self.cam_translation[0], self.min_[1], 0., 1.,
            -self.cam_translation[0], self.max_[1], 0., 1.,
            self.min_[0], -self.cam_translation[1], 0., 1.,
            self.max_[0], -self.cam_translation[1], 0., 1.,
        ]

    def load_box(self, box, density):
        loader = self.loaders.get(box, {}).get(density)

        if not loader:
            # TODO on complete, remove the previous LOD
            box_loader = self.loaders.setdefault(box, {})
            # box_loader[density] = True
            # self.fetch_data(box, density)
            box_loader[density] = t = Thread(
                target=self.fetch_data, args=[box, density])
            t.daemon = True
            t.start()

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.touches.remove(touch)
            self.touches_center = self.get_center()
            self.touches_dist = self.get_dist(self.touches_center)
            return True
        else:
            return super(View, self).on_touch_up(touch)

    def get_center(self):
        return (
            sum(t.x for t in self.touches) / float(len(self.touches)),
            sum(t.y for t in self.touches) / float(len(self.touches))
        ) if self.touches else self.center

    def get_dist(self, center):
        return (sum(
            dist(t.pos, center)
            for t in self.touches
        ) / float(len(self.touches))) if self.touches else 0

    def load_low(self, filename):
        self.lock = Lock()
        self.low_loaded = False

        self.indexes = {}
        with open(filename + '.indexes') as f_indexes:
            for l in f_indexes:
                box, indexes = l.split(':')
                self.indexes[
                    tuple(int(x) for x in box.split(','))
                ] = [int(x) for x in indexes.split(',')]

        self.model = f = las.File(filename)

        self.model_offset = f.header.offset
        self.model_scale = scale = f.header.get_scale()

        self.min_ = min_ = [
            (f.header.min[i] - self.model_offset[i]) / scale[i]
            for i in range(3)
        ]

        self.max_ = max_ = [
            (f.header.max[i] - self.model_offset[i]) / scale[i]
            for i in range(3)
        ]

        self.add_grid(
            min_,
            max_, 10, 20)

        Clock.schedule_once(self.go_to_origin)
        # self.fetch_data(density=.001)
        self.low_loaded = True

    def go_to_origin(self, *args):
        for x in range(3):
            self.cam_translation[x] = -(self.max_[x] - self.min_[x]) / 2

        self.cam_translation[2] -= 1 / self.model_scale[2] * 100
        self.obj_scale = self.model_scale[0] / 10

    def fetch_data(self, box=None, density=None):
        rendering = self

        l = 0
        points = []
        f = self.model

        if box is None:
            i_min = 0
            i_max = len(f)
        else:
            i_min = self.indexes[box][0]
            i_max = self.indexes[box][1]

        o_x, o_y, o_z = self.model_offset
        s_x, s_y, s_z = self.model_scale

        for i in xrange(i_min, i_max, int(1 / density)):
            # if di and i % densities[di - 1]:
            #     continue
            with self.lock:
                p = f.read(i)
            x = (p.x - o_x) / s_x
            y = (p.y - o_y) / s_y
            z = (p.z - o_z) / s_z
            lum = max(0, min(p.intensity, 160)) / 160.

            # print p.color.red, p.color.green, p.color.blue
            point = (x, y, z, lum)
            # print point
            points.extend(point)
            if l < 2 ** 12 - 1:
                l += 1
            else:
                rendering.add(points)
                print i
                l = 0
                points = []
            i += 1

        rendering.add(points)


KV = '''
#:import listdir os.listdir
#:import A kivy.animation.Animation

<Button>:
    font_name: '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'

FloatLayout:
    BoxLayout:
        orientation: 'vertical'
        BoxLayout:
            size_hint_y: None
            height: 48
            Label:
                text: 'x: {}'.format(rendering.cam_translation[0])
            Label:
                text: 'y: {}'.format(rendering.cam_translation[1])
            Label:
                text: 'z: {}'.format(rendering.cam_translation[2])
            Label:
                text: 'rx: {}'.format(rendering.cam_rotation[0])
            Label:
                text: 'ry: {}'.format(rendering.cam_rotation[1])
            Label:
                text: 'rz: {}'.format(rendering.cam_rotation[2])

            Label:
                size_hint_x: None
                width: self.texture_size[0]
                text: 'vec: {}'.format(rendering.direction_vector)

            Label:
                text: '{}'.format(rendering.nb_points)
        View:
            id: rendering
            obj_scale: scale.value if scale.value > 0 else 1

        BoxLayout:
            size_hint_y: None
            height: self.minimum_height

            GridLayout:
                cols: 1
                Slider:
                    min: .00001
                    max: .001
                    id: scale
                    value: rendering.obj_scale

                Label:
                    size_hint_y: .1
                    text: 'scale: {}'.format(scale.value)


            GridLayout:
                size_hint: None, None
                size: 200, 200
                cols: 3
                Button:
                    text: '↟'
                    on_press: rendering.cam_rotation[0] += 5
                Button:
                    text: '—'
                    on_press: rendering.cam_rotation[0] = 0
                Button:
                    text: '↡'
                    on_press: rendering.cam_rotation[0] -= 5
                Button:
                    text: '↻'
                    on_press: rendering.cam_rotation[2] += 5
                Button:
                    text: '↑'
                    on_press:
                        vec = rendering.direction_vector
                        rendering.cam_translation[0] += vec[0] * 10000
                        rendering.cam_translation[1] += vec[1] * 10000
                        rendering.cam_translation[2] += vec[2] * 10000
                Button:
                    text: '↺'
                    on_press: rendering.cam_rotation[2] -= 5
                Button:
                    text: '←'
                    on_press: rendering.cam_translation[0] -= 1
                Button:
                    text: '↓'
                    on_press:
                        vec = rendering.direction_vector
                        rendering.cam_translation[0] -= vec[0] * 10000
                        rendering.cam_translation[1] -= vec[1] * 10000
                        rendering.cam_translation[2] -= vec[2] * 10000
                Button:
                    text: '→'
                    on_press: rendering.cam_translation[0] += 100000

                Button:
                    text: 'x+'
                    on_press: rendering.cam_translation[0] += 100000
                Button:
                    text: 'y+'
                    on_press: rendering.cam_translation[1] += 100000
                Button:
                    text: 'z+'
                    on_press: rendering.cam_translation[2] += 100000

                Button:
                    text: 'x-'
                    on_press: rendering.cam_translation[0] -= 100000
                Button:
                    text: 'y-'
                    on_press: rendering.cam_translation[1] -= 100000
                Button:
                    text: 'z-'
                    on_press: rendering.cam_translation[2] -= 100000

                Button:
                    text: 'go'
                    on_press:
                        rendering.cam_translation[0] = -5500000
                        rendering.cam_translation[1] = -4000000
                        rendering.cam_translation[2] = -100000
                        rendering.cam_rotation[0] = -100
                        rendering.cam_rotation[2] = -100
                        rendering.obj_scale = 8 * 10 ** -5
                ToggleButton:
                    text: 'grid'
                    on_state:
                        if self.state == 'normal': rendering.rendering.remove(rendering.grid)
                        else: rendering.rendering.add(rendering.grid)

                ToggleButton:
                    text: 'tile'
                    on_state:
                        if self.state == 'normal': rendering.rendering.remove(rendering.tile)
                        else: rendering.rendering.add(rendering.tile)

                ToggleButton:
                    text: 'cross'
                    on_state:
                        if self.state == 'normal': rendering.rendering.remove(rendering.cross)
                        else: rendering.rendering.add(rendering.cross)
'''  # noqa


class App3D(App):
    def build(self):
        root = Builder.load_string(KV)
        # XXX hack to force setup_scene call
        root.ids.rendering.mode = 'points'
        import sys
        t = Thread(target=root.ids.rendering.load_low, args=[sys.argv[1]])
        t.daemon = True
        t.start()
        return root


def main():
    App3D().run()


if __name__ == '__main__':
    main()
