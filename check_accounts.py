import json

with open('quark_config.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('账号列表:')
for i, account in enumerate(data['cookies']):
    print(f'{i}: {account["name"]}')
