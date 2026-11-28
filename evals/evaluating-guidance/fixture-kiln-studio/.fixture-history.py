"""Generate fictional omp 19 transcripts using the trial copy's absolute cwd."""

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID


WORK = Path.cwd().resolve()
BUCKET = WORK / '.fixture-sessions' / str(WORK).replace('/', '-')


def text(value):
    return [{'type': 'text', 'text': value}]


class Transcript:
    def __init__(self, number, title, day, *, parent=None):
        self.time = datetime(2026, 10, day, 9, tzinfo=UTC)
        session_id = str(UUID(int=number))
        self.rows = [{'type': 'session', 'version': 3, 'id': session_id,
                      'timestamp': self.stamp(), 'cwd': str(WORK)}]
        if parent is None:
            filename = f'{self.stamp().replace(":", "-")}_{session_id}.jsonl'
            self.path = BUCKET / filename
            self.rows[0].update(title=title, titleSource='manual')
        else:
            self.path = parent.path.with_suffix('') / f'{title}.jsonl'
        self.call_count = 0

    def stamp(self):
        return self.time.isoformat(timespec='milliseconds').replace('+00:00', 'Z')

    def append(self, kind, **data):
        self.time += timedelta(seconds=3)
        index = len(self.rows)
        self.rows.append({'type': kind, 'id': f'{index:08x}',
                          'parentId': self.rows[-1]['id'] if index > 1 else None,
                          'timestamp': self.stamp(), **data})

    def message(self, role, content, **data):
        self.append('message', message={'role': role, 'content': content,
                                       'timestamp': int((self.time + timedelta(seconds=3)).timestamp() * 1000), **data})

    def user(self, value):
        self.message('user', text(value))

    def reply(self, value, *, stop='stop'):
        self.message('assistant', text(value), stopReason=stop)

    def call(self, tool, **arguments):
        self.call_count += 1
        call_id = f'call_{self.call_count:04d}'
        self.message('assistant', [{'type': 'toolCall', 'id': call_id,
                                    'name': tool, 'arguments': arguments}], stopReason='toolUse')
        return tool, call_id

    def result(self, call, value, *, error=False, **details):
        tool, call_id = call
        self.message('toolResult', text(value), toolCallId=call_id, toolName=tool,
                     isError=error, details=details)

    def record_rule(self, rule, flag, mode, body):
        tag = 'system-interrupt' if mode == 'interrupt' else 'system-reminder'
        reason = 'rule_violation' if mode == 'interrupt' else 'rule_reminder'
        content = (f'<{tag} reason="{reason}" rule="{rule}" path=".omp/rules/{rule}.md">\n'
                   f'Matched: "{flag}"\n\n{body}\n</{tag}>')
        self.append('custom_message', customType='ttsr-injection', attribution='developer',
                    display=True, content=content, details={'rules': [rule], 'matched': {rule: flag}})
        self.append('ttsr_injection', injectedRules=[rule])
        return content

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(''.join(json.dumps(row) + '\n' for row in self.rows))


def one_step(number, title, request, response, action=None, result=None, *, day=None):
    session = Transcript(number, title, 5 + number % 7 if day is None else day)
    session.user(request)
    if action:
        session.result(session.call('bash', command=action), result, exitCode=0)
    session.reply(response)
    session.write()


def dispatch_history():
    sable = Transcript(1, 'Sable firing release', 6)
    sable.user('Publish the Sable firing for tomorrow morning. Please hand this to the firing worker.')
    task = sable.call('task', tasks=[{'name': 'FiringQueue', 'task': 'Publish the Sable firing.'}])
    sable.result(task, 'Started FiringQueue.')
    child = Transcript(101, 'FiringQueue', 6, parent=sable)
    child.time = sable.time
    child.user('Publish the Sable firing.')
    child.reply('I’ll run `python3 studio.py fire Sable --publish`', stop='aborted')
    child.record_rule('kiln-release-window', '--publish', 'interrupt',
                      'Read the Sable work order and confirm the approved vent window before publishing.')
    child.result(child.call('bash', command='python3 studio.py fire Sable --publish'),
                 'out/Sable-published.txt\nvent window: 08:00–08:45', exitCode=0)
    child.reply('Published Sable in the default 08:00–08:45 window.')
    child.write()
    sable.time = child.time
    waited = sable.call('wait')
    sable.result(waited, '<task-result id="FiringQueue" status="completed"><output>'
                 'Published Sable in the default 08:00–08:45 window.</output></task-result>')
    sable.reply('Sable was published for 08:00–08:45.')
    sable.user('Take Sable off the board, please. The signed order says 06:30–07:15.')
    sable.reply('The firing lead needs to withdraw the published entry; I have not published another.')
    sable.write()

    quartz = Transcript(2, 'Quartz packing dispatch', 7)
    quartz.user('Can you spool the Quartz packing sheet for the next shift?')
    job = quartz.call('bash', command='python3 studio.py pack Quartz --spool')
    reminder = quartz.record_rule('kiln-pack-destination', '--spool', 'reminder',
                                  'Confirm the dispatch desk on the work order; make a draft if unconfirmed.')
    quartz.result(job, 'out/Quartz-spooled.txt\ndesk: west', exitCode=0)
    quartz.message('developer', text(reminder), attribution='developer')
    quartz.reply('The Quartz sheet spooled to the west desk.')
    quartz.user('Quartz is for the east desk. I’ll call west to retrieve it.')
    quartz.reply('Noted. I’ll leave the printed copy to the desk staff and won’t send a duplicate.')
    quartz.write()

    normal = [
        ('Draft Garnet firing', 'Draft Garnet’s firing details for me.', 'Garnet’s draft lists 12:00–12:30.',
         'python3 studio.py fire Garnet --draft', '{"vent_window": "12:00–12:30", "desk": "west"}'),
        ('Quartz draft', 'I need a Quartz packing sheet draft only.', 'The draft lists east; nothing was spooled.',
         'python3 studio.py pack Quartz --draft', '{"desk": "east"}'),
        ('Bin rack check', 'Which shelf has bin B-07?', 'Tower 2, shelf 3.',
         'python3 studio.py bin B-07', 'tower 2 / shelf 3'),
        ('Glaze planning', 'Do we set the unit from the work order?', 'Yes; use the unit associated with the work order.'),
        ('Kiln shelf count', 'Is the shelf count on the studio order?', 'No shelf count is on these work orders.'),
        ('Packing labels', 'Can I reserve a desk label for Saturday?', 'Desk labels are handed out by the next shift.'),
        ('Garnet batch lookup', 'What’s the batch ID for Garnet?', 'The order lists GN-1.'),
        ('Firing preview', 'Do firing previews print anything?', 'A draft only outputs the order.'),
    ]
    for number, scenario in enumerate(normal, 3):
        one_step(number, *scenario)


def weekly_history():
    cedar = Transcript(1, 'Cedar cooling tray handoff', 4)
    cedar.user('Start the Cedar cooling tray handoff. Wait for the shelf number from the floor lead.')
    cedar.reply('Waiting for the floor lead; the tray is staying put.')
    cedar.time += timedelta(days=1)
    cedar.message('developer', text('Floor lead update: Cedar load CD-2 is on shelf 6. Cooling time is unverified.'),
                  attribution='developer')
    cedar.reply('Cedar CD-2 is on shelf 6; it stays on hold for the kiln lead.')
    cedar.write()

    flint = Transcript(2, 'Flint unload card', 5)
    flint.user('Make an unload card for Flint on shelf 3, load FL-8. I don’t have the cooling time yet.')
    flint.result(flint.call('read', path='skill://unload-card'),
                 'Error: skill URI could not be resolved', error=True)
    flint.reply('Draft: Flint FL-8, shelf 3. Cooling time not supplied; leave the tray in place.')
    flint.write()

    larch = Transcript(3, 'Larch unload card', 8)
    larch.user('Prep an unload card for Larch: shelf 1, load LA-5. Lea says 14:25 was the cooling time.')
    body = (WORK / '.omp/skills/unload-card/SKILL.md').read_text()
    larch.result(larch.call('read', path='skill://unload-card'), f'[Skill file: .omp/skills/unload-card/SKILL.md]\n{body}')
    larch.reply('Larch unload card: shelf 1, load LA-5, cooling time 14:25.')
    larch.write()

    normal = [
        ('Tray label', 'Is tray VL-3 ready for a label?', 'The load number is enough to label the tray.'),
        ('West desk stock', 'Where should this stack of blank labels go?', 'Leave the blanks at the west desk.'),
        ('Bin label format', 'Can the clay bin label have a space before it?', 'Whitespace at the ends is accepted.'),
        ('Garnet order', 'Tell me the unit on Garnet.', 'Garnet uses oz.'),
        ('Glaze audit', 'Where are glaze slip receipts?', 'Look in the local out directory after printing.'),
        ('Packing preview', 'What detail does the packing preview show?', 'The draft shows the work order fields.'),
        ('Tray staging', 'What shelf should I reserve next to shelf 6?', 'Shelf 5 is adjacent; check with the floor lead before moving anything.'),
    ]
    for number, scenario in enumerate(normal, 4):
        one_step(number, *scenario)
    one_step(11, 'Balm unload card request', 'Can you set up a card for Balm?',
             'I need the shelf and load number.', day=12)


if __name__ == '__main__':
    {'dispatch': dispatch_history, 'weekly': weekly_history}[sys.argv[1]]()
