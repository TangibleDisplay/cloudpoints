from liblas.file import File as Las
from os.path import expanduser
from sys import argv
INF = float('inf')

f_input = Las(expanduser(argv[1]))
index_file = argv[2] + '.indexes'

boxes = {}

CUT = 100

x_min, y_min, _ = f_input.header.min
x_max, y_max, _ = f_input.header.max
z_min, z_max = INF, -INF

for i, p in enumerate(f_input):
    z_min = min(z_min, p.z)
    z_max = max(z_max, p.z)
    if not i % 1000:
        print('.',)

    box = (
        100 * (p.x - x_min) // (x_max - x_min),
        100 * (p.y - y_min) // (y_max - y_min)
    )

    b = boxes.setdefault(box, [])
    b.append(i)

h = f_input.header
h.min = x_min, y_min, z_min
h.max = x_max, y_max, z_max
print("z_min, z_max", z_min, z_max)

f_output = Las(expanduser(argv[2]), mode='w', header=h)
i = 0

print("done building boxes")
with open(index_file, mode='w') as f_indexes:
    f_indexes.write('{},{}\n'.format(CUT, CUT))

    for x in range(CUT):
        print('\n{}\t'.format(x),)
        for y in range(CUT):
            print('.',)
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
