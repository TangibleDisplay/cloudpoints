/* simple.glsl

simple diffuse lighting based on laberts cosine law; see e.g.:
    http://en.wikipedia.org/wiki/Lambertian_reflectance
    http://en.wikipedia.org/wiki/Lambert%27s_cosine_law
*/
---VERTEX SHADER-------------------------------------------------------
#ifdef GL_ES
    precision highp float;
#endif

attribute vec3 v_pos;
attribute float lum;

uniform mat4 modelview_mat;
uniform mat4 projection_mat;

varying vec4 vertex_pos;
varying float vertex_lum;

void main (void) {
    //compute vertex position in eye_sapce and normalize normal vector
    vec4 pos = modelview_mat * vec4(v_pos,1.0);
    vertex_pos = pos;
    vertex_lum = lum;
    gl_Position = projection_mat * pos;
}


---FRAGMENT SHADER-----------------------------------------------------
#ifdef GL_ES
    precision highp float;
#endif

varying vec4 vertex_pos;
varying float vertex_lum;

void main (void){
    gl_FragColor = vec4(1.0, 1.0, 1.0, vertex_lum);
}
