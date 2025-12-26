import json

with open('quark_config.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

account_index = 1
account_name = data['cookies'][account_index]['name']
task_count = len(data['cookies'][account_index]['tasklist'])
print(f'账号 {account_name} (索引 {account_index}) 当前有 {task_count} 个任务')
print('最近添加的6个任务:')

# 确保我们有足够的任务
start_index = max(0, task_count - 6)
for i in range(start_index, task_count):
    task = data['cookies'][account_index]['tasklist'][i]
    print(f'  {i}: {task["taskname"]} - {task["shareurl"]}')

# 检查添加的任务是否正确
print('\n验证添加的任务:')
expected_tasks = [
    '测试批量任务1',
    '测试批量任务2', 
    '测试批量任务3',
    '文件测试任务1',
    '文件测试任务2',
    '文件测试任务3'
]

for task_name in expected_tasks:
    found = False
    for task in data['cookies'][account_index]['tasklist']:
        if task['taskname'] == task_name:
            found = True
            break
    status = '✓' if found else '✗'
    print(f'{status} {task_name}')
