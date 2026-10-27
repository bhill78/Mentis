"""Count b-tree and overflow pages without decoding any column value.

The format is SQLite's fileformat2: cell sizes use the local-payload formula
for table leaves and index cells. Rowid varints are stepped over, not returned.
"""


def btree_pages(path, rootpages):
    with open(path, 'rb') as source:
        header = source.read(100)
        if len(header) != 100 or header[:16] != b'SQLite format 3\0':
            raise ValueError('not a SQLite file')
        size = int.from_bytes(header[16:18], 'big')
        size = 65536 if size == 1 else size
        if size < 512 or size > 65536 or size & (size - 1):
            raise ValueError('invalid page size')
        usable = size - header[20]
        source.seek(0, 2)
        count = source.tell() // size
        visited = set()

        def page(number):
            if not 1 <= number <= count or number in visited:
                raise ValueError('invalid or repeated page pointer')
            visited.add(number)
            source.seek((number - 1) * size)
            data = source.read(size)
            if len(data) != size:
                raise ValueError('short page')
            return data

        def uint(data, start, length):
            if start < 0 or start + length > usable:
                raise ValueError('invalid cell pointer')
            return int.from_bytes(data[start:start+length], 'big')

        def varint(data, start):
            value = 0
            for n in range(9):
                byte = uint(data, start+n, 1)
                value = (value << (8 if n == 8 else 7)) | (byte if n == 8 else byte & 127)
                if byte < 128 or n == 8:
                    return value, start+n+1
            raise ValueError('invalid varint')

        result = {}
        for root in rootpages:
            before = len(visited)
            pending = [root]
            while pending:
                number = pending.pop()
                data = page(number)
                offset = 100 if number == 1 else 0
                kind = uint(data, offset, 1)
                if kind not in (2, 5, 10, 13):
                    raise ValueError('invalid b-tree page type')
                cells = uint(data, offset+3, 2)
                interior = kind in (2, 5)
                pointers = offset + (12 if interior else 8)
                if interior:
                    pending.append(uint(data, offset+8, 4))
                for index in range(cells):
                    cell = uint(data, pointers+2*index, 2)
                    if interior:
                        pending.append(uint(data, cell, 4))
                        cell += 4
                    if kind == 5:
                        continue
                    payload, cell = varint(data, cell)
                    if kind == 13:
                        _, cell = varint(data, cell)
                    minimum = ((usable-12)*32//255)-23
                    maximum = usable-35 if kind == 13 else ((usable-12)*64//255)-23
                    if payload > maximum:
                        local = minimum + (payload-minimum) % (usable-4)
                        if local > maximum:
                            local = minimum
                        overflow = uint(data, cell+local, 4)
                        remaining = payload-local
                        while remaining > 0:
                            block = page(overflow)
                            overflow = uint(block, 0, 4)
                            remaining -= usable-4
                        if overflow:
                            raise ValueError('overflow chain longer than payload')
            result[root] = len(visited)-before
        return result
