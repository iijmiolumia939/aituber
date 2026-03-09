import re

with open('AITuber/Assets/Animations/AvatarAnimatorController.controller', encoding='utf-8') as f:
    content = f.read()

states_of_interest = ['Walk', 'WalkStart', 'WalkStop', 'WalkStopStart', 'SadIdle', 'SadKick', 'SitIdle', 'SitLaugh', 'IdleAlt', 'Nod', 'Shake', 'Laugh']
blocks = re.split(r'(?=^--- )', content, flags=re.MULTILINE)
found = {}
for block in blocks:
    for s in states_of_interest:
        if re.search(r'm_Name: ' + re.escape(s) + r'\b', block):
            m = re.search(r'm_Motion: \{(.+?)\}', block)
            found[s] = m.group(1) if m else 'NOT FOUND'

for s in states_of_interest:
    print(f'{s:20s} -> {found.get(s, "NOT IN CONTROLLER")}')

# 全ステートのmotion状況も出す
print()
print('=== ALL STATES ===')
idle_guid = 'fd8695750dfad5c4598bc13ef4e74d24'
walk_guids = {
    '03f97c90ebf32b24ba6ba1e1bc17dc0a': 'Female_Walk',
    '6768ef573e415fe40b255f45156701b1': 'Female_StartWalk',
    'b7a3ac141830a7d49912991997335401': 'Female_StopWalk',
    'c8b33cc866f0e2341b2816ac1607c892': 'Female_StopStartWalk',
}
states = re.findall(r'm_Name: (\S+).*?m_Motion: \{(fileID: [^,\}]+)(?:, guid: ([a-f0-9]+))?.*?\}', content, re.DOTALL)
for name, fileid, guid in states:
    if fileid == 'fileID: 0':
        tag = 'EMPTY'
    elif guid == idle_guid:
        tag = 'IDLE_PLACEHOLDER'
    elif guid in walk_guids:
        tag = 'WALK_OK:' + walk_guids[guid]
    else:
        tag = 'has_clip'
    print(f'{tag:30s} {name}  fileID={fileid}  guid={guid}')
