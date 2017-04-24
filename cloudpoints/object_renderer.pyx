from base64 import b64decode
import io

from uuid import uuid4
from kivy.uix.widget import Widget
from kivy.graphics.fbo import Fbo
from kivy.graphics import (
    Callback, PushMatrix, PopMatrix, Rotate, Translate, Scale,
    Rectangle, Color, Mesh, UpdateNormalMatrix, Canvas,
    InstructionGroup, BindTexture
)
from kivy.graphics.transformation import Matrix
from kivy.core.image import Image as CoreImage
from kivy.graphics.opengl import (
    glBlendFunc, GL_FALSE, glEnable, glDisable)
from kivy.properties import (
    StringProperty, ListProperty, ObjectProperty, NumericProperty,
    DictProperty)

from kivy.clock import Clock, mainthread

VS = '''
#ifdef GL_ES
    precision highp float;
#endif

attribute vec3 v_pos;
attribute float lum;

uniform mat4 modelview_mat;
uniform mat4 projection_mat;

varying vec4 vertex_pos;
varying float vertex_lum;

float dist(vec3 pos) {
    return pow(pow(pos.x, 2.) + pow(pos.y, 2.) + pow(pos.z, 2.), .5);
}

void main (void) {
    //compute vertex position in eye_space and normalize normal vector
    vec4 pos = modelview_mat * vec4(v_pos, 1.0);
    vertex_pos = pos;
    gl_Position = projection_mat * pos;
    float d = dist(vertex_pos.xyz);
    gl_PointSize = 10. / d;
    vertex_lum = lum * (1 - d / 1000.);
}
'''

FS = '''
#version 120
#ifdef GL_ES
    precision highp float;
#endif

uniform sampler2D tex;

varying vec4 vertex_pos;
varying float vertex_lum;

float dist(vec2 pos) {
    return pow(pow(pos.x, 2.) + pow(pos.y, 2.), .5);
}

void main (void){
    vec4 col = texture2D(tex, gl_PointCoord);
    gl_FragColor = vec4(col.r, col.g, col.b, col.a * vertex_lum);
}
'''

# base64 conversion of png texture
POINT_TEXTURE = b64decode('''
iVBORw0KGgoAAAANSUhEUgAAAAoAAAAKCAQAAAAnOwc2AAAAAmJLR0QA/4ePzL8AAAAJcEhZcwAA
CxMAAAsTAQCanBgAAAAHdElNRQfhAx8JICD/LWB7AAAAGXRFWHRDb21tZW50AENyZWF0ZWQgd2l0
aCBHSU1QV4EOFwAAAJFJREFUCNc9zj1LQlEAgOHnXA4JikIggh+pWOik0Nbu73dRF1MHRQkk6IYE
IXKPQ9g7PeMbSCNDbQPkDvbeYxoZejPxhNzWgqjj1dRAFb+aHpyjnrG+mgxlLS+OUV1LRRAESfSo
kbkX/iXz6cOPpFAoXOVO0c5SV6aKi5ONdXQwUzLWlXzbmNvGsEqw84yvv/kbCqMrgSb2mY8AAAAA
SUVORK5CYII=''')


GL_PROGRAM_POINT_SIZE = 0x8642
GL_POINT_SPRITE = 0x8861
GL_BLEND = 0x0BE2
GL_SRC_ALPHA = 0x0302
GL_ONE = 0x0001
GL_ONE_MINUS_SRC_ALPHA = 0x0303


class DataRenderer(Widget):
    obj_translation = ListProperty([0, 0, 0])
    obj_rotation = ListProperty([0, 0, 0])
    obj_scale = NumericProperty(1)
    texture = ObjectProperty(None, allownone=True)
    cam_translation = ListProperty([0, 0, 0])
    cam_rotation = ListProperty([0, 0, 0])
    light_sources = DictProperty()
    mode = StringProperty('')
    data = ListProperty([])
    nb_points = NumericProperty()

    def __init__(self, **kwargs):
        glEnable(GL_PROGRAM_POINT_SIZE)
        glEnable(GL_POINT_SPRITE)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        self.canvas = Canvas()
        self.meshes = []
        with self.canvas:
            self.fbo = Fbo(size=self.size,
                           with_depthbuffer=True,
                           compute_normal_mat=True,
                           clear_color=(0., 0., 0., 0.))

            self.viewport = Rectangle(size=self.size, pos=self.pos)

        self.fbo.shader.vs = VS
        self.fbo.shader.fs = FS

        print("shader:", self.fbo.shader.source)
        rotate_cam = Clock.create_trigger(self._rotate_cam, timeout=.01)
        self.bind(cam_rotation=rotate_cam)

        move_cam = Clock.create_trigger(self._move_cam, timeout=.01)
        self.bind(cam_translation=move_cam)

        super(DataRenderer, self).__init__(**kwargs)

    def _rotate_cam(self, *args):
        self.cam_rot_x.angle = self.cam_rotation[0]
        self.cam_rot_y.angle = self.cam_rotation[1]
        self.cam_rot_z.angle = self.cam_rotation[2]

    def _move_cam(self, *args):
        self.cam_translate.xyz = self.cam_translation
        self.cam_rot_x.origin = [-x for x in self.cam_translate.xyz]
        self.cam_rot_y.origin = [-x for x in self.cam_translate.xyz]
        self.cam_rot_z.origin = [-x for x in self.cam_translate.xyz]

    def on_obj_scale(self, *args):
        self.scale.xyz = [self.obj_scale, ] * 3

    def on_light_sources(self, *args):
        self.fbo['light_sources'] = [
            ls[:] for ls in self.light_sources.values()]
        self.fbo['nb_lights'] = len(self.light_sources)

    def on_mode(self, *args):
        self.setup_canvas()

    def setup_canvas(self, *args):
        print('setting up the scene')
        with self.fbo:
            self.cb = Callback(self.setup_gl_context)
            PushMatrix()
            self.setup_scene()
            PopMatrix()
            data = io.BytesIO(POINT_TEXTURE)
            im = CoreImage(data, ext="png")
            BindTexture(texture=im.texture, index=1)
            self.cb = Callback(self.reset_gl_context)

    def on_size(self, instance, value):
        self.fbo.size = value
        self.viewport.texture = self.fbo.texture
        self.viewport.size = value
        self.update_glsl()

    def on_pos(self, instance, value):
        self.viewport.pos = value

    def on_texture(self, instance, value):
        self.viewport.texture = value

    def setup_gl_context(self, *args):
        self.fbo.clear_buffer()

    def reset_gl_context(self, *args):
        pass

    def update_glsl(self, *args):
        asp = self.width / float(self.height)
        proj = Matrix().view_clip(-asp, asp, -1, 1, 1, 100, 1)
        self.fbo['projection_mat'] = proj
        self.fbo['tex'] = 1
        # view = Matrix()
        # fovy = 90.
        # view.perspective(
        #     fovy,
        #     asp,
        #     0.001,
        #     self.obj_scale * 10 ** 7,
        # )
        # self.fbo['modelview_mat'] = view

    def add(self, data):
        m = Mesh(
            fmt=[('v_pos', 3, 'float'), ('lum', 1, 'float')],
            mode='points',
            vertices=data,
            indices=range(len(data) / 4)
        )
        self.nb_points += len(data) / 4
        uid = uuid4()
        self.meshes[uid] = m
        self.show(uid)
        # self.rendering.add(m)
        return uid
        # print("added mesh", m)
        self.rendering.add(m)

    @mainthread
    def show(self, mesh_uid):
        mesh = self.meshes[mesh_uid]
        # XXX probably very inneficient, would be better to put the info
        # in the mesh itself
        if mesh not in self.rendering.children:
            self.rendering.add(mesh)

    @mainthread
    def hide(self, mesh_uid):
        mesh = self.meshes[mesh_uid]
        # XXX see show()
        if mesh in self.rendering.children:
            self.rendering.remove(mesh)

    @mainthread
    def add_grid(self, min_, max_, medium_range, high_range):
        vertices = []
        for intensity, current_range in [
            (.5, medium_range), (.35, high_range)
        ]:
            for i in range(2):
                step = (max_[i] - min_[i]) / current_range
                x = min_[i]

                while x <= max_[i]:
                    vert1 = [float(min_[j]) for j in range(3)] + [float(intensity)]
                    vert2 = [float(max_[j]) for j in range(3)] + [float(intensity)]

                    vert1[i] = float(x)
                    vert2[i] = float(x)
                    x += step

                    vertices.extend(vert1 + vert2)

        self.grid = Mesh(
            fmt=[('v_pos', 3, 'float'), ('lum', 1, 'float')],
            mode='lines',
            vertices=vertices,
            indices=range(len(vertices) / 4)
        )

        # self.rendering.add(self.grid)

        self.tile = Mesh(
            fmt=[('v_pos', 3, 'float'), ('lum', 1, 'float')],
            mode='triangle_fan',
            vertices=[0, 0, 0, 0] * 4,
            indices=range(4)
        )

        # self.rendering.add(self.tile)

        self.cross = Mesh(
            fmt=[('v_pos', 3, 'float'), ('lum', 1, 'float')],
            mode='lines',
            vertices=[0, 0, 0, 0] * 4,
            indices=range(4))

        # self.rendering.add(self.cross)

    def setup_scene(self):
        Color(1, 1, 1, 0)

        PushMatrix()
        # asp = self.width / float(self.height)
        # view = Matrix()
        # fovy = 90.
        # view.perspective(
        #     fovy,
        #     asp,
        #     0.001,
        #     self.obj_scale * 10 ** 7,
        # )
        # self.fbo['modelview_mat'] = view
        self.scale = Scale(self.obj_scale)
        self.cam_translate = Translate(self.cam_translation)
        self.cam_rot_x = Rotate(self.cam_rotation[0], 1, 0, 0)
        self.cam_rot_y = Rotate(self.cam_rotation[1], 0, 1, 0)
        self.cam_rot_z = Rotate(self.cam_rotation[2], 0, 0, 1)
        UpdateNormalMatrix()
        self.rendering = InstructionGroup()
        PopMatrix()
