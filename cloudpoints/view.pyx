# encoding: utf-8
from kivy.config import Config

from math import cos, sin, radians, exp
from kivy.core.window import Window  # noqa
from kivy.lang import Builder
from kivy.properties import AliasProperty, DictProperty, ListProperty
from kivy.clock import Clock, mainthread
from kivy.app import App
from threading import Thread
from liblas import file as las
from itertools import dropwhile
from time import sleep

from cloudpoints.object_renderer import DataRenderer

SYNC = False


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
    meshes = DictProperty()
    box_queue = ListProperty()
    '''
    motion of the camera, on x, y, z, at each frame the camera will be
    moved along the x, y, z direction *according to its own orientation,
    projected on the xy plane*

    for example, [0, 1, 0] will set the camera in a forward motion,
    [-1, 0, 0] will strafe to the left, [0, 0, 1] will move down.
    '''
    cam_motion = ListProperty([0, 0, 0])

    def __init__(self, **kwargs):
        super(View, self).__init__(**kwargs)
        self.touches = []
        self.touches_center = []
        self.touches_dist = 0
        Clock.schedule_interval(self.update_cam, 0)
        self.loaded_boxes = set()
        self._stop = False

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
        touches = self.touches

        motion = self.cam_motion
        if motion[0]:
            vec = cross(self.direction_vector, (0, 0, 1))
            self.cam_translation[0] -= dt * motion[0] * vec[0] / self.model_scale[0]
            self.cam_translation[1] -= dt * motion[0] * vec[1] / self.model_scale[1]
            self.cam_translation[2] -= dt * motion[0] * vec[2] / self.model_scale[2]


        if motion[1]:
            vec = cross(cross(self.direction_vector, (0, 0, 1)), (0, 0, 1))
            self.cam_translation[0] -= dt * motion[1] * vec[0] / self.model_scale[0]
            self.cam_translation[1] -= dt * motion[1] * vec[1] / self.model_scale[1]
            self.cam_translation[2] -= dt * motion[1] * vec[2] / self.model_scale[2]

        if motion[2]:
            self.cam_translation[2] -= dt * motion[2] * 1. / self.model_scale[2]

        if len(self.touches) == 1:
            rot = self.cam_rotation[:]
            rot[2] -= touches[0].dx / 10.  # pitch
            rot[0] += touches[0].dy / 10.  # yaw
            rot[0] = max(-180, min(0, rot[0]))
            self.cam_rotation = rot

        if len(self.touches) > 1:
            t = self.touches[0]
            t.push()
            t.apply_transform_2d(self.to_widget)

            c = self.get_center()
            d = self.get_dist(c)

            vec = self.direction_vector
            zoom = min(1, max(-1, (d - self.touches_dist) / 5.))

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
            ct[0] += (vec[0] * zoom + strafe_vector[0] / 5.) * 10000
            ct[1] += (vec[1] * zoom + strafe_vector[1] / 5.) * 10000
            ct[2] += (vec[2] * zoom + strafe_vector[2] / 5.) * 10000

            self.touches_center = c
            self.touches_dist = d

            t.pop()


    def get_boxes(self):
        x_cut, y_cut = self.cut_size

        min_ = self.min_
        max_ = self.max_
        x, y, z = [-v for v in self.cam_translation]
        # x, y, z = self.cam_translation

        x_min, y_min, z_min = min_
        x_max, y_max, z_max = max_

        x_inc = (x_max - x_min) / x_cut
        y_inc = (y_max - y_min) / y_cut

        for Xi in xrange(x_cut):
            for Yi in xrange(y_cut):
                if (Xi, Yi) not in self.indexes:
                    # print "ignoring {},{}".format(Xi, Yi)
                    continue

                X = x_min + Xi * x_inc + x_inc / 2
                Y = y_min + Yi * y_inc + y_inc / 2
                # estimate: the floor must be around 1/3rd of the scene
                # height
                Z = (z_min + z_max) / 4

                yield((Xi, Yi), dist3((X, Y, Z), (x, y, z)))

    def on_cam_translation(self, *args):
        self.update_lod()

    def update_lod(self, *args):
        boxes = sorted(self.get_boxes(), key=lambda x: x[1])

        max_distance = dist3(self.min_, self.max_)
        # min_density = 0.001
        distances = [
            (exp(x / 4.) * max_distance * .01, (1. / exp(x / 2.)))
            for x in xrange(0, 11)
        ]

        min_distance = boxes[0][1]
        self.obj_scale = (
            (1 - (min_distance / max_distance) ** 2) *
            self.model_scale[0]
        )

        self.box_queue = []
        for i, (box, distance) in enumerate(boxes):
            c = list(dropwhile(lambda x: x[0] < distance, distances))
            if not c:
                continue
            density = c[0][1]
            if box in self.indexes:
                self.load_box(box, density)

        self.cross.vertices = [
            -self.cam_translation[0], self.min_[1], 0., 1.,
            -self.cam_translation[0], self.max_[1], 0., 1.,
            self.min_[0], -self.cam_translation[1], 0., 1.,
            self.max_[0], -self.cam_translation[1], 0., 1.,
        ]

    def load_box(self, box, density):
        if (
            (box, density) not in self.box_queue and
            (box, density) not in self.loaded_boxes
        ):
            self.box_queue.append((box, density))

    def on_touch_up(self, touch):
        if touch.grab_current is self:
            touch.ungrab(self)
            self.touches.remove(touch)

            if self.touches:
                t = self.touches[0]
                t.push()
                t.apply_transform_2d(self.to_widget)

            self.touches_center = self.get_center()
            self.touches_dist = self.get_dist(self.touches_center)

            if self.touches:
                t.pop()
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
        self.indexes = {}
        with open(filename + '.indexes') as f_indexes:
            self.cut_size = [
                int(x) for x in
                f_indexes.readline().strip().split(',')
            ]
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

        t = Thread(target=self.data_fetcher)
        t.daemon = True
        t.start()

    def go_to_origin(self, *args):
        for x in range(3):
            self.cam_translation[x] = -(self.max_[x] - self.min_[x]) / 2
            self.cam_rotation[x] = 0


    def data_fetcher(self):
        print "data fetcher started"
        while True:
            if self.box_queue:
                box, density = self.box_queue.pop(0)
                print "loading {}:{}".format(box, density)
                self.fetch_data(box=box, density=density)
                self.loaded_boxes.add((box, density))
            else:
                sleep(.1)

    def fetch_data(self, box=None, density=None):

        rendering = self
        self.meshes[(box, density)] = meshes = []

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
            if self._stop:
                print("stopping thread")
                return
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
                meshes.append(rendering.add(points))
                # rendering.add(points)
                print('nb_points', i)
                l = 0
                points = []
            i += 1

        meshes.append(rendering.add(points))
        # rendering.add(points)

    def stop(self):
        self.box_queue = []
        self._stop = True

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
                        rendering.go_to_origin()
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
        if SYNC:
            root.ids.rendering.load_low(sys.argv[1])
        else:
            t = Thread(target=root.ids.rendering.load_low, args=[sys.argv[1]])
            t.daemon = True
            t.start()
        return root


def main():
    App3D().run()


if __name__ == '__main__':
    main()
