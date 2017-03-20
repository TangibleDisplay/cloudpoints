from liblas.file import File as Las
from os.path import expanduser
from sys import argv

f_input = Las(expanduser(argv[1]))
f_output = Las(expanduser(argv[2]), mode='w', header=f_input.header)
index_file = argv[2] + '.indexes'

boxes = {}

CUT = 100

x_min, y_min, _ = f_input.header.min
x_max, y_max, _ = f_input.header.max

for i, p in enumerate(f_input):
    box = (
        100 * (p.x - x_min) // (x_max - x_min),
        100 * (p.y - y_min) // (y_max - y_min)
    )

    b = boxes.setdefault(box, [])
    b.append(i)

i = 0
with open(index_file, mode='w') as f_indexes:
    for x in range(CUT):
        for y in range(CUT):
            box = boxes.get((x, y))
            if not box:
                continue

            for p in box:
                f_output.write(f_input.read(p))

                box = boxes.get((x, y))
                if not box:
                    continue

            f_indexes.write('{},{}:{},{}\n'.format(x, y, i, i + len(box)))
            i += len(box)
