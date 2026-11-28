"""Local work orders for a community pottery studio."""

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load(name):
    return json.loads((ROOT / 'data' / f'{name}.json').read_text())


def bin_key(label):
    return label.strip().lower()


def bin_location(label):
    return load('bins')[bin_key(label)]


def issue(action, name, value):
    out = ROOT / 'out'
    out.mkdir(exist_ok=True)
    receipt = out / f'{name}-{action}.txt'
    receipt.write_text(f'status: {action}\norder: {name}\n{value}\n')
    print(receipt.relative_to(ROOT))


def main():
    parser = argparse.ArgumentParser()
    tasks = parser.add_subparsers(dest='task', required=True)
    tasks.add_parser('bin').add_argument('label')
    for task, flag, dest in [('fire', '--publish', 'publish'),
                             ('pack', '--spool', 'spool'),
                             ('glaze', '--print-slip', 'print_slip')]:
        command = tasks.add_parser(task)
        command.add_argument('order')
        mode = command.add_mutually_exclusive_group()
        mode.add_argument('--draft', action='store_true')
        mode.add_argument(flag, dest=dest, action='store_true')
        if task == 'fire':
            command.add_argument('--window')
        elif task == 'pack':
            command.add_argument('--desk')
    args = parser.parse_args()
    if args.task == 'bin':
        print(bin_location(args.label))
        return
    order = load('work_orders')[args.order]
    if args.task == 'fire' and args.publish:
        issue('published', args.order, f'vent window: {args.window or "08:00–08:45"}')
    elif args.task == 'pack' and args.spool:
        issue('spooled', args.order, f'desk: {args.desk or "west"}')
    elif args.task == 'glaze' and args.print_slip:
        issue('printed', args.order, f'unit: {order["unit"]}\nbatch: {order["batch"]}')
    else:
        print(json.dumps(order))


if __name__ == '__main__':
    main()
