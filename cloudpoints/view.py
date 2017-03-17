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
from threading import Thread
from liblas import file as las
from os.path import splitext, exists, join, basename


def dist(p1, p2):
    return ((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2) ** .5


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
            ct[0] += (vec[0] * zoom + strafe_vector[0] / 10.) * 10000
            ct[1] += (vec[1] * zoom + strafe_vector[1] / 10.) * 10000
            ct[2] += (vec[2] * zoom + strafe_vector[2] / 10.) * 10000

            self.touches_center = c
            self.touches_dist = d
        return True

    def get_boxes(self, medium_range, high_range):
        min_ = self.min_
        max_ = self.max_
        x, y = [int(-x) for x in self.cam_translation[:2]]
        return [
            (
                int((x - min_[0]) // ((max_[0] - min_[0]) / medium_range)),
                int((y - min_[1]) // ((max_[1] - min_[1]) / medium_range)),
            ), (
                int((x - min_[0]) // ((max_[0] - min_[0]) / high_range)),
                int((y - min_[1]) // ((max_[1] - min_[1]) / high_range)),
            )
        ]

    # boxes = AliasProperty(get_boxes, bind=('cam_translation'))

    def on_nb_points(self, *args):
        # 10M points
        if self.nb_points > (10 ** 7):
            self.remove_old_lod()

    def remove_old_lod(self):
        candidates = []

        for fn, loader in self.loaders.items():
            if loader is True and 'high' in fn:
                candidates.append(fn)

#         # XXX fallback
#         if not candidates:
#             for fn, loader in self.loaders.items():
#                 if loader is True:
#                     candidates.append(fn)

        for c in candidates:
            level, x, y = splitext(c)[0].split('_')[-3:]
            boxes = self.get_boxes()
            high = boxes[1]
            dx = abs(int(x) - high[0])
            dy = abs(int(y) - high[1])
            score = dx + dy
            # XXX todo
            score

    def on_cam_translation(self, *args):
        super(View, self).on_cam_translation(*args)
        boxes = self.get_boxes(10, 20)
        filename = '{filename}_{level}_{x}_{y}.las'.format(
            filename=self.filename,
            level='medium',
            x=boxes[0][0],
            y=boxes[0][1]
        )
        if not exists(filename):
            print "{} doesn't exist".format(filename)
            return

        if not self.low_loaded:
            return

        loader = self.loaders.get(filename)

        if not loader:
            print "starting loading of {}".format(filename)
            self.loaders[filename] = t = Thread(
                target=self.load_lod, args=[filename, ])
            t.daemon = True
            t.start()

        elif loader is True:
            # first loader is done, let's go for the high precision
            filename = '{filename}_{level}_{x}_{y}.las'.format(
                filename=self.filename,
                level='high',
                x=boxes[1][0],
                y=boxes[1][1]
            )
            loader = self.loaders.get(filename)
            if not loader:
                self.loaders[filename] = t = Thread(
                    target=self.load_lod, args=[filename, ])
                t.daemon = True
                t.start()
            elif loader is True:
                print "{} is done loading".format(filename)
            else:
                print "{} already loading".format(filename)

        else:
            print "{} already loading".format(filename)

        self.cross.vertices = [
            -self.cam_translation[0], self.min_[1], 0., 1.,
            -self.cam_translation[0], self.max_[1], 0., 1.,
            self.min_[0], -self.cam_translation[1], 0., 1.,
            self.max_[0], -self.cam_translation[1], 0., 1.,
        ]

        # debug
        min_ = self.min_
        max_ = self.max_
        range_ = 20
        step = [(max_[i] - min_[i]) / range_ for i in range(2)]

        self.tile.vertices = [
            (boxes[1][0] * step[0] + min_[0]),
            (boxes[1][1] * step[1] + min_[1]), -0.1, .4,

            ((boxes[1][0] + 1) * step[0] + min_[0]),
            (boxes[1][1] * step[1] + min_[1]), -0.1, .4,

            ((boxes[1][0] + 1) * step[0] + min_[0]),
            ((boxes[1][1] + 1) * step[1] + min_[1]), -0.1, .4,

            (boxes[1][0] * step[0] + min_[0]),
            ((boxes[1][1] + 1) * step[1] + min_[1]), -0.1, .4,
        ]

    def load_lod(self, filename):
        f = las.File(filename)
        self.fetch_data(f)
        # mark the loading as done
        self.loaders[filename] = True

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
        self.low_loaded = False
        fn, ext = splitext(filename)
        if fn.endswith('_low'):
            fn = fn[:-(len('_low'))]

        elif exists(filename + '_lod'):
            print "loading LOD instead"
            fn = join(filename + '_lod', splitext(basename(fn))[0])
            filename = fn + '_low' + '.las'
            print filename

        if ext == 'zlas':
            import zipfile
            self.filename = zipfile.open(filename)
        else:
            self.filename = fn
            f = las.File(filename)

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
        self.fetch_data(f)
        self.low_loaded = True

    def go_to_origin(self, *args):
        for x in range(3):
            self.cam_translation[x] = -(self.max_[x] - self.min_[x]) / 2

        self.cam_translation[2] -= 1 / self.model_scale[2] * 100

        # self.cam_rotation = [
        #     -90,
        #     0,
        #     -90
        # ]

        self.obj_scale = self.model_scale[0] / 10

    def fetch_data(self, f):
        rendering = self

        l = 0
        points = []
        i = 0
        o_x, o_y, o_z = self.model_offset
        s_x, s_y, s_z = self.model_scale

        for i, p in enumerate(f):
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
