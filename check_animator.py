import re

with open('AITuber/Assets/Animations/AvatarAnimatorController.controller', encoding='utf-8') as f:
    content = f.read()

# 1. パラメータ一覧
print('=== Parameters ===')
params = re.findall(r'm_Name: (\S+)\s+m_Type: (\d+)', content)
for name, t in params:
    ptype = {'1': 'Float', '3': 'Bool', '9': 'Trigger', '4': 'Int'}.get(t, t)
    print(f'  {name}: {ptype}')

# 2. Any State からのトランジション条件一覧
print()
print('=== Any State Transitions (m_ConditionEvent) ===')
transitions = re.findall(r'm_ConditionEvent: (\S+)', content)
from collections import Counter
for name, cnt in sorted(Counter(transitions).items()):
    print(f'  {name}: {cnt}x')

# 3. Walk ステートへのトランジション先 (DstState)
print()
print('=== Blocks with Walk trigger ===')
blocks = re.split(r'(?=^--- )', content, flags=re.MULTILINE)
for block in blocks:
    if 'm_ConditionEvent: Walk' in block and 'AnimatorStateTransition' in block:
        dst = re.search(r'm_DstState: \{fileID: (-?\d+)', block)
        exit_t = re.search(r'm_HasExitTime: (\d)', block)
        dur = re.search(r'm_TransitionDuration: ([\d.]+)', block)
        print(f'  DstState fileID={dst.group(1) if dst else "?"} HasExitTime={exit_t.group(1) if exit_t else "?"} Duration={dur.group(1) if dur else "?"}')
        # DstStateのfileIDからステート名を探す
        if dst:
            fid = dst.group(1)
            for b2 in blocks:
                if '&' + fid in b2.split('\n')[0] if b2.strip() else False:
                    n = re.search(r'm_Name: (\S+)', b2)
                    print(f'    -> state name: {n.group(1) if n else "?"}')
