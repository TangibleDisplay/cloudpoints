CloudPoints
===========

A cloudpoint visualisation widget based on Kivy and LibLas.

For optimisation, this library uses index_las.py to order a las file into
blocks of known dimensions, and be able to load them depending on the camera
position. Then the visualisation will use a multipass approach to load the view
at the right level of detail.

Hopefully more documentation later.

A demonstration of usage can be seen at:
https://www.youtube.com/watch?v=Umls6ytXasU
