"""Convert persisted mappings to independent source/target rows."""
from copy import deepcopy
import uuid
from multi_mapping import migrate_record


def server_label(server):
    if server == 'local':
        return '本机'
    parts = server.split('|')
    if len(parts) == 4 and parts[1] == '-l':
        port, _, user, host = parts
        return f'{user}@{host}' + (f':{port}' if port != '22' else '')
    return parts[-1]


def direction_label(record):
    return ' → '.join(server_label(item['server']) for item in record['locations'])


def expand_records(records):
    rows = []
    for original in records:
        record = migrate_record(original)
        for target in record['targets']:
            row = deepcopy(record)
            row['locations'] = [deepcopy(record['locations'][i]) for i in (record['source'], target)]
            row['source'], row['targets'] = 0, [1]
            row['id'] = record.get('id', uuid.uuid4().hex) if len(record['targets']) == 1 else uuid.uuid4().hex
            rows.append(row)
    return rows
